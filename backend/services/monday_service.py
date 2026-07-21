import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file if available
load_dotenv()


class MondayClient:
    """Client for interacting with the Monday.com GraphQL v2 API."""

    API_URL = "https://api.monday.com/v2"

    def __init__(self, api_key: str | None = None):
        """
        Initialize the MondayClient.

        Args:
            api_key: Optional Monday.com API Key. If not provided, it is loaded
                     from the MONDAY_API_KEY environment variable.

        Raises:
            ValueError: If no API key is provided or found in the environment.
        """
        self.api_key = api_key or os.getenv("MONDAY_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MONDAY_API_KEY environment variable is not set and no API key was provided."
            )

        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "API-Version": "2023-10",
        }

    def _execute_query(self, query: str, variables: dict | None = None) -> dict:
        """
        Execute a GraphQL query against the Monday.com API.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            dict: JSON response from the API.

        Raises:
            RuntimeError: If the HTTP request fails or GraphQL returns errors.
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(
                self.API_URL, json=payload, headers=self.headers, timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"HTTP request to Monday.com API failed: {e}") from e

        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"Monday.com API GraphQL errors: {data['errors']}")

        return data

    def fetch_board_items(self, board_id: str) -> list[dict]:
        """
        Fetch all items from a specified Monday.com board using cursor-based pagination.

        Args:
            board_id: The ID of the Monday.com board to query.

        Returns:
            list[dict]: A list of raw GraphQL item dictionaries.
        """
        if not board_id:
            raise ValueError("board_id must be provided.")

        all_items = []
        cursor = None

        # Initial page query via boards -> items_page
        initial_query = """
        query ($board_id: [ID!]) {
          boards(ids: $board_id) {
            items_page(limit: 500) {
              cursor
              items {
                id
                name
                column_values {
                  id
                  text
                  value
                  column {
                    title
                  }
                }
              }
            }
          }
        }
        """

        # Next page query via next_items_page
        next_query = """
        query ($cursor: String!) {
          next_items_page(limit: 500, cursor: $cursor) {
            cursor
            items {
              id
              name
              column_values {
                id
                text
                value
                column {
                  title
                }
              }
            }
          }
        }
        """

        while True:
            if cursor is None:
                response_data = self._execute_query(
                    initial_query, {"board_id": [str(board_id)]}
                )
                boards = response_data.get("data", {}).get("boards", [])
                if not boards:
                    break
                items_page = boards[0].get("items_page", {})
            else:
                response_data = self._execute_query(next_query, {"cursor": cursor})
                items_page = response_data.get("data", {}).get("next_items_page", {})

            page_items = items_page.get("items", [])
            all_items.extend(page_items)

            cursor = items_page.get("cursor")
            if not cursor or not page_items:
                break

        return all_items

    def parse_items_to_dicts(self, items: list[dict]) -> list[dict]:
        """
        Flatten nested GraphQL item JSON structures into flat dictionaries suitable for Pandas.

        Args:
            items: List of raw GraphQL item dictionaries.

        Returns:
            list[dict]: Flattened list of dictionaries with column titles as keys and text as values.
        """
        parsed_list = []

        for item in items:
            row = {
                "id": item.get("id"),
                "name": item.get("name"),
            }

            for col in item.get("column_values", []):
                col_title = None
                if col.get("column") and isinstance(col["column"], dict):
                    col_title = col["column"].get("title")

                if not col_title:
                    col_title = col.get("id")

                if col_title:
                    row[col_title] = col.get("text")

            parsed_list.append(row)

        return parsed_list
