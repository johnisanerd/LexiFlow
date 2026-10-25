import os
import re
import json
import csv
import argparse
from apify_client import ApifyClient
import requests

# Default regions for Phase 1 as per strategy
DEFAULT_REGIONS = [
    "Miami, FL", "Tampa, FL", "Orlando, FL", "Jacksonville, FL", "St. Petersburg, FL",
    "Houston, TX", "Dallas, TX", "Austin, TX",
    "Los Angeles, CA", "San Francisco, CA",
    "New York, NY",
    "Chicago, IL"
]

DEFAULT_QUERIES = ["Personal Injury Law Firm", "Family Law Firm"]

def split_city_state(address):
    """
    Pulls ("City", "ST") from a US address such as "100 Main St, Miami, FL 33131".
    """
    match = re.search(r"([^,]+),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?(?:,\s*(?:USA?|United States))?\s*$", address or "")
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2)

class LeadSourcer:
    def __init__(self, apify_token=None, apollo_api_key=None):
        self.apify_token = apify_token or os.getenv("APIFY_API_TOKEN")
        self.apollo_api_key = apollo_api_key or os.getenv("APOLLO_API_KEY")
        
        if self.apify_token:
            self.apify_client = ApifyClient(self.apify_token)
        else:
            self.apify_client = None
            print("Warning: APIFY_API_TOKEN not set. Scraper functionality will be disabled.")

    def scrape_google_maps(self, regions, queries, max_results=10):
        """
        Uses Apify's Google Maps Scraper to find law firms.
        """
        if not self.apify_client:
            print("Error: Apify client not initialized.")
            return []

        search_queries = []
        for region in regions:
            for query in queries:
                search_queries.append(f"{query} in {region}")

        print(f"Starting Apify scrape for {len(search_queries)} queries...")
        
        # Example actor ID for Google Maps Scraper
        actor_id = "johnvc/google-maps-places-api"
        run_input = {
            "searchTerms": search_queries,
            # The actor returns at least 20 places per search; extras are dropped below
            "maxResultsPerSearch": max(max_results, 20),
            "language": "en",
        }

        # Run the actor and wait for it to finish
        run = self.apify_client.actor(actor_id).call(run_input=run_input)
        # apify-client 3.x returns a Run object, 2.x returns a dict
        dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]

        leads = []
        per_search = {}
        for item in self.apify_client.dataset(dataset_id).iterate_items():
            term = item.get("searchTerm")
            per_search[term] = per_search.get(term, 0) + 1
            if per_search[term] > max_results:
                continue
            city, state = split_city_state(item.get("address"))
            lead = {
                "name": item.get("title"),
                "address": item.get("address"),
                "city": city,
                "state": state,
                "website": item.get("website"),
                "phone": item.get("phoneNumber"),
                "category": item.get("type"),
                "rating": item.get("rating"),
                "reviews_count": item.get("ratingCount"),
            }
            leads.append(lead)
        
        print(f"Scraped {len(leads)} leads from Google Maps.")
        return leads

    def enrich_with_apollo(self, lead):
        """
        Uses Apollo.io API to find the Managing Partner / Owner.
        """
        if not self.apollo_api_key:
            # Fallback mock logic for pilot
            lead["managing_partner"] = "Unknown"
            lead["email"] = "Unknown"
            return lead

        domain = lead.get("website", "").replace("http://", "").replace("https://", "").split("/")[0]
        if not domain:
            lead["managing_partner"] = "Unknown"
            lead["email"] = "Unknown"
            return lead

        url = "https://api.apollo.io/v1/people/match"
        payload = {
            "api_key": self.apollo_api_key,
            "domain": domain,
            "titles": ["Managing Partner", "Owner", "Founding Partner", "Attorney"]
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                person = data.get("person", {})
                lead["managing_partner"] = person.get("name", "Unknown")
                lead["email"] = person.get("email", "Unknown")
            else:
                lead["managing_partner"] = "Unknown"
                lead["email"] = "Unknown"
        except Exception as e:
            print(f"Error enriching lead {lead['name']}: {e}")
            lead["managing_partner"] = "Unknown"
            lead["email"] = "Unknown"

        return lead

    def save_to_csv(self, leads, filename):
        if not leads:
            print("No leads to save.")
            return

        keys = leads[0].keys()
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(leads)
        print(f"Saved {len(leads)} leads to {filename}")

    def save_to_json(self, leads, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(leads, f, indent=4)
        print(f"Saved {len(leads)} leads to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Automated Law Firm Lead Sourcer")
    parser.add_argument("--regions", nargs="+", default=DEFAULT_REGIONS, help="List of cities/regions to search")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES, help="List of search terms")
    parser.add_argument("--limit", type=int, default=5, help="Max results per query")
    parser.add_argument("--output", default="sourced_leads.csv", help="Output filename")
    parser.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format")
    parser.add_argument("--dry-run", action="store_true", help="Simulate scraping without calling APIs")

    args = parser.parse_args()

    sourcer = LeadSourcer()

    if args.dry_run:
        print("Dry run enabled. Simulating data for Florida...")
        # Mock data based on Florida pilot
        leads = [
            {"name": "Ferrer Law, PA", "address": "Miami, FL", "website": "https://www.ferrerlawpa.com/", "managing_partner": "Patricia Ferrer"},
            {"name": "Leighton Law", "address": "Miami, FL", "website": "https://www.leightonlaw.com/", "managing_partner": "John Elliott Leighton"},
            {"name": "Esposito Law Firm", "address": "Tampa, FL", "website": "https://www.espositofirm.com/", "managing_partner": "Brian Esposito"}
        ]
    else:
        raw_leads = sourcer.scrape_google_maps(args.regions, args.queries, max_results=args.limit)
        leads = []
        for lead in raw_leads:
            enriched_lead = sourcer.enrich_with_apollo(lead)
            leads.append(enriched_lead)

    if args.format == "csv":
        sourcer.save_to_csv(leads, args.output)
    else:
        sourcer.save_to_json(leads, args.output)

if __name__ == "__main__":
    main()
