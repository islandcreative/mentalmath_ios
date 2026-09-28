import os
import sys
import json
import re
import subprocess
from google import genai
from google.genai import types

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command '{cmd}' notice: {result.stderr.strip()}")
    return result.stdout

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    issue_number = os.getenv("ISSUE_NUMBER", "")

    if not api_key:
        print("Error: Missing GEMINI_API_KEY")
        sys.exit(1)

    # 1. Fetch live Issue title and body using GitHub CLI
    raw_issue = run_command(f"gh issue view {issue_number} --json title,body")
    try:
        issue_json = json.loads(raw_issue)
        issue_title = issue_json.get("title", "")
        issue_body = issue_json.get("body", "")
    except Exception as e:
        print(f"Failed to fetch issue metadata via gh CLI: {e}")
        sys.exit(1)

    # 2. Determine diff budget from ticket specification
    max_lines = 150
    if "Max Diff Lines: 80" in issue_body or "Small" in issue_body:
        max_lines = 90
    elif "Max Diff Lines: 250" in issue_body or "Medium" in issue_body:
        max_lines = 260

    # Extract target files mentioned in backticks with .swift
    target_files = re.findall(r"`([a-zA-Z0-9_\-\./]+\.swift)`", issue_body)
    target_files = list(set(target_files))

    # Read current state of target files (if they exist)
    file_context = {}
    for f in target_files:
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as file:
                file_context[f] = file.read()
        else:
            file_context[f] = "[New File to Create]"

    client = genai.Client(api_key=api_key)

    system_instruction = """
    You are an expert iOS Engineer working with modern SwiftUI and SwiftData.
    Your task is to implement the requested ticket by outputting the exact full content for each affected file.
    
    Rules:
    - Write clean, production-ready Swift code using SwiftData and SwiftUI.
    - Always include an accompanying unit test file (XCTest or Swift Testing).
    - Output must be strict JSON mapping file paths to their full updated or new string contents.
    - Format: {"files": [{"path": "relative/path.swift", "content": "file contents..."}]}
    """

    prompt = f"""
    Ticket Title: {issue_title}
    
    Ticket Specification:
    {issue_body}
    
    Existing Files Context:
    {json.dumps(file_context, indent=2)}
    
    Implement the changes and generate the unit test file.
    """

    # 3. Invoke Gemini 2.5 Flash
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    try:
        data = json.loads(response.text)
        files_to_write = data.get("files", [])
    except Exception as e:
        print(f"Failed to parse model response: {e}")
        with open("alert_comment.md", "w") as f:
            f.write("⚠️ **Dev Agent Parsing Error**: Model response was not valid JSON.")
        sys.exit(1)

    # 4. Write files
    for item in files_to_write:
        path = item.get("path")
        content = item.get("content")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # 5. Circuit Breaker: Strict Diff Inspection
    lines_added = 0
    lines_deleted = 0
    numstat = run_command("git diff --numstat")
    for line in numstat.strip().split("\n"):
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                lines_added += int(parts[0]) if parts[0].isdigit() else 0
                lines_deleted += int(parts[1]) if parts[1].isdigit() else 0

    total_diff = lines_added + lines_deleted
    print(f"Total diff: {total_diff} lines (Budget: {max_lines})")

    if total_diff > max_lines:
        alert_msg = (
            f"⚠️ **Dev Agent Circuit Breaker Triggered**\n\n"
            f"The generated code changes exceeded the allowed budget.\n"
            f"- **Allowed:** {max_lines} lines\n"
            f"- **Attempted:** {total_diff} lines ({lines_added} added, {lines_deleted} removed)\n\n"
            f"Run aborted to protect project stability and token budget. Please break this ticket into smaller tasks."
        )
        with open("alert_comment.md", "w") as f:
            f.write(alert_msg)
        sys.exit(2)

    print("Diff inspection passed successfully.")

if __name__ == "__main__":
    main()
