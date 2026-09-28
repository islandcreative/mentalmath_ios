import os
import glob
import re
from google import genai
from google.genai import types

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Missing GEMINI_API_KEY")
        return

    # 1. Collect all Swift files in the Models directory
    model_files = glob.glob("**/Models/**/*.swift", recursive=True)
    if not model_files:
        model_files = glob.glob("**/*.swift", recursive=True)

    collected_models = {}
    for path in model_files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            # Only include files defining @Model
            if "@Model" in content:
                collected_models[path] = content

    if not collected_models:
        print("No @Model classes found.")
        return

    # 2. Prompt Gemini Flash to compile the Schema Reference doc
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are a technical documentation specialist.
    Analyze the following SwiftData @Model files from an iOS project and generate a clean, comprehensive markdown reference document.

    Requirements:
    1. Provide an executive summary of the entity graph and relationship delete rules.
    2. Document each model's purpose, attributes, constraints, and relationships.
    3. Include copy-pasteable Swift model snippets.
    4. Provide recommended SwiftUI #Predicate patterns for common query use cases.

    Swift Source Files:
    {collected_models}
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
        )
    )

    # 3. Save to docs/Schema_Reference.md
    os.makedirs("docs", exist_ok=True)
    output_path = "docs/Schema_Reference.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)

    print(f"Updated {output_path} successfully.")

if __name__ == "__main__":
    main()
