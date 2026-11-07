
from app.services.csv_importer import import_websites


# Sample CSV data
sample_csv = """company_name,website_url
Example Company,https://example.com
Demo Store,https://demo.com
Invalid Company,not-a-valid-url
Missing URL,
"""


# Convert string into bytes
file_content = sample_csv.encode("utf-8")


# Run CSV importer
result = import_websites(file_content)


# Display results
print("\n========== CSV IMPORT TEST ==========")
print("Success:", result["success"])
print("Total valid websites:", result.get("total_websites", 0))
print("Invalid rows:", result.get("invalid_rows", 0))

print("\nValid Websites:")
for website in result.get("websites", []):
    print(website)

print("\nErrors:")
for error in result.get("errors", []):
    print(error)

print("\n=====================================")
