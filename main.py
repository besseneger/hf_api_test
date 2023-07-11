import os
import unicodedata

from collections import namedtuple
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv
from loguru import logger

from utils.common_func import get_cells, get_args, get_xlsx_file_path
from utils.hf_api import get_hf_data, post_request, upload_file


def get_candidate_file_path(position_path: Path, candidate_name: str):
    candidate_name = unicodedata.normalize('NFKC', candidate_name).strip().lower()
    for file in position_path.iterdir():
        file_name = unicodedata.normalize('NFKC', Path(file).stem).strip().lower()

        if candidate_name == file_name:
            continue

        return file

    return


def get_vacancy_id_by_name(vacancies: list, vacancy_name: str):
    for vacancy in vacancies:
        position: str = vacancy.get("position")
        vacancy_id: int = vacancy.get("id")

        if position.strip().lower() != vacancy_name.strip().lower():
            continue

        return vacancy_id

    return


def get_vacancies(
        base_url: str,
        org_id: str,
        headers: dict,
) -> list:

    params = {
        "page": 1,
    }

    page_data = get_hf_data(base_url, f"accounts/{org_id}/vacancies", headers, params)
    total_pages = page_data["total_pages"]
    vacancies: list = page_data["items"]

    if page_data["total_pages"] > 1:
        for page in range(1, total_pages):
            params["page"] += 1
            page_data = get_hf_data(base_url, f"accounts/{org_id}/vacancies", headers, params)
            vacancies.extend(page_data["items"])

    return vacancies


def prepare_candidate_body(full_name: str, money: str,) -> dict:
    first_name = full_name.split()[0]
    last_name = full_name.split()[1]

    body = {
        "first_name": first_name,
        "last_name": last_name,
        "money": money,
    }

    if len(full_name.split()) > 2:
        middle_name = full_name.split()[2]
        body["middle_name"] = middle_name

    return body


def create_candidate(
        base_url: str,
        org_id: str,
        headers: dict,
        body: dict,
):

    return post_request(base_url, f"accounts/{org_id}/applicants", headers, body)


def get_vacancy_status_id(
        base_url: str,
        org_id: str,
        headers: dict,
        search_status: str,

):
    params = {}
    end_point = f"accounts/{org_id}/vacancies/statuses"
    statuses = get_hf_data(base_url, end_point, headers, params)["items"]

    for status in statuses:
        status_name: str = status.get("name").strip()
        status_id: int = status.get("id")

        if status_name != search_status.strip():
            continue

        return status_id

    return

def main():
    db_path = get_args()

    try:
        if not Path(db_path).exists():
            raise FileNotFoundError
    except FileNotFoundError:
        logger.error(f"Directory '{db_path}' not found.")
        return

    try:
        xlsx_file = get_xlsx_file_path(db_path)
    except FileNotFoundError:
        logger.error(f"There is no xlsx-file found in directory '{db_path}'. Exit.")
        return

    candidates = get_cells(xlsx_file, 5, 5)

    column_name = [
        "position",
        "full_name",
        "salary",
        "comment",
        "status",
    ]
    Row = namedtuple(
        "Row",
        column_name,
    )

    load_dotenv()

    org_id = os.environ["ORG_ID"]
    base_url = os.environ["URL"]
    hf_token = os.environ["TOKEN"]

    headers = {
        "Authorization": f"Bearer {hf_token}",
    }

    vacancies = get_vacancies(base_url, org_id, headers)

    for candidate_id, candidate in enumerate(candidates, 1):
        current_row = Row(*candidate)
        candidate_body = prepare_candidate_body(current_row.full_name, current_row.salary)
        file_path = Path.joinpath(db_path, current_row.position)
        candidate_file = get_candidate_file_path(file_path, current_row.full_name)
        vacancy_id = get_vacancy_id_by_name(vacancies, current_row.position)
        uploaded_file_id = upload_file(base_url, f"accounts/{org_id}/upload", headers, candidate_file)["id"]
        candidate_id = create_candidate(base_url, org_id, headers, candidate_body)["id"]
        status_id = get_vacancy_status_id(base_url, org_id, headers, current_row.status)
        logger.info("Processing candidate: {}. "
                    "File path: {}. Vacancy id: {}".format(current_row.full_name.strip(),
                                           candidate_file, vacancy_id))
        vacancy_body = {
            "vacancy": vacancy_id,
            "status": status_id,
            "comment": current_row.comment,
            "files": [uploaded_file_id]
        }

        pprint(post_request(base_url, f"accounts/{org_id}/applicants/{candidate_id}/vacancy", headers, vacancy_body))

        logger.info("Candidate processed.")


if __name__ == '__main__':
    main()
