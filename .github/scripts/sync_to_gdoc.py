import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive"
]

def main():
    sa_key_json = os.getenv("GCP_SA_KEY")
    doc_id = os.getenv("SCHEMA_DOC_ID")
    schema_path = "docs/Schema_Reference.md"

    if not sa_key_json or not doc_id:
        print("Missing GCP_SA_KEY or SCHEMA_DOC_ID environment variable.")
        return

    if not os.path.exists(schema_path):
        print(f"File {schema_path} does not exist. Nothing to sync.")
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        markdown_content = f.read()

    # Authenticate via service account
    key_info = json.loads(sa_key_json)
    credentials = service_account.Credentials.from_service_account_info(
        key_info, scopes=SCOPES
    )
    docs_service = build("docs", "v1", credentials=credentials)

    # Fetch document metadata to find current end index
    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])
    
    # Calculate end index (Docs API requires explicit text indices)
    end_index = 1
    if content:
        end_index = max(1, content[-1].get("endIndex", 1) - 1)

    requests = []

    # 1. Clear existing document body if it has text
    if end_index > 1:
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index
                }
            }
        })

    # 2. Insert updated Markdown text at the beginning
    requests.append({
        "insertText": {
            "location": {
                "index": 1
            },
            "text": markdown_content
        }
    })

    # Execute atomic batch update
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests}
    ).execute()

    print(f"Successfully pushed {schema_path} to Google Doc (ID: {doc_id}).")

if __name__ == "__main__":
    main()
