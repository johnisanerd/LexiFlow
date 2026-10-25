"""
Offline test for the Google Maps step of source_leads.py.

The Apify client is mocked, so no token or network is needed:
    python3 -m unittest scripts/test_source_leads.py
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import source_leads

# Dataset items shaped like the actor's output (made-up firms)
PLACES = [
    {
        "searchTerm": "Personal Injury Law Firm in Miami, FL",
        "position": 1,
        "title": "Example Injury Law, PA",
        "address": "100 SE 2nd St Suite 3000, Miami, FL 33131",
        "latitude": 25.7743,
        "longitude": -80.1912,
        "rating": 4.8,
        "ratingCount": 312,
        "type": "Personal injury attorney",
        "types": ["Personal injury attorney", "Law firm"],
        "phoneNumber": "(305) 555-0100",
        "website": "https://www.example.com/",
        "placeId": "ChIJexample000000000000001",
    },
    {
        "searchTerm": "Personal Injury Law Firm in Miami, FL",
        "position": 2,
        "title": "Sample Accident Lawyers",
        "address": "200 Ponce de Leon Blvd, Coral Gables, FL 33134",
        "latitude": 25.7506,
        "longitude": -80.2592,
        "rating": 4.6,
        "ratingCount": 98,
        "type": "Lawyer",
        "types": ["Lawyer"],
        "phoneNumber": "(305) 555-0101",
        "website": "https://www.example.org/",
        "placeId": "ChIJexample000000000000002",
    },
    {
        "searchTerm": "Family Law Firm in Miami, FL",
        "position": 1,
        "title": "Placeholder Family Law Group",
        "address": "300 Brickell Ave, Miami, FL 33131, United States",
        "latitude": 25.7650,
        "longitude": -80.1918,
        "rating": 5.0,
        "ratingCount": 41,
        "type": "Family law attorney",
        "types": ["Family law attorney"],
        "phoneNumber": "(305) 555-0102",
        "website": "https://www.example.net/",
        "placeId": "ChIJexample000000000000003",
    },
]


class ScrapeGoogleMapsTest(unittest.TestCase):
    def run_scrape(self, run, max_results):
        with mock.patch.object(source_leads, "ApifyClient") as client_cls:
            client = client_cls.return_value
            client.actor.return_value.call.return_value = run
            client.dataset.return_value.iterate_items.return_value = iter(PLACES)
            sourcer = source_leads.LeadSourcer(apify_token="placeholder")
            leads = sourcer.scrape_google_maps(["Miami, FL"], ["Personal Injury Law Firm", "Family Law Firm"], max_results=max_results)
        return client, leads

    def test_maps_actor_output_to_lead_fields(self):
        # apify-client 3.x returns a Run object with attributes
        client, leads = self.run_scrape(SimpleNamespace(default_dataset_id="dataset-1"), max_results=1)

        client.actor.assert_called_once_with("johnvc/google-maps-places-api")
        client.actor.return_value.call.assert_called_once_with(run_input={
            "searchTerms": ["Personal Injury Law Firm in Miami, FL", "Family Law Firm in Miami, FL"],
            "maxResultsPerSearch": 20,
            "language": "en",
        })
        client.dataset.assert_called_once_with("dataset-1")
        self.assertEqual(leads, [
            {
                "name": "Example Injury Law, PA",
                "address": "100 SE 2nd St Suite 3000, Miami, FL 33131",
                "city": "Miami",
                "state": "FL",
                "website": "https://www.example.com/",
                "phone": "(305) 555-0100",
                "category": "Personal injury attorney",
                "rating": 4.8,
                "reviews_count": 312,
            },
            {
                "name": "Placeholder Family Law Group",
                "address": "300 Brickell Ave, Miami, FL 33131, United States",
                "city": "Miami",
                "state": "FL",
                "website": "https://www.example.net/",
                "phone": "(305) 555-0102",
                "category": "Family law attorney",
                "rating": 5.0,
                "reviews_count": 41,
            },
        ])

    def test_accepts_dict_run_from_older_client(self):
        # apify-client 2.x returns the run as a dict
        client, leads = self.run_scrape({"defaultDatasetId": "dataset-2"}, max_results=25)

        client.actor.return_value.call.assert_called_once_with(run_input={
            "searchTerms": ["Personal Injury Law Firm in Miami, FL", "Family Law Firm in Miami, FL"],
            "maxResultsPerSearch": 25,
            "language": "en",
        })
        client.dataset.assert_called_once_with("dataset-2")
        self.assertEqual([lead["name"] for lead in leads], [place["title"] for place in PLACES])
        self.assertEqual((leads[1]["city"], leads[1]["state"]), ("Coral Gables", "FL"))

    def test_split_city_state(self):
        self.assertEqual(source_leads.split_city_state("221 W N Loop Blvd, Austin, TX 78751"), ("Austin", "TX"))
        self.assertEqual(source_leads.split_city_state("1 Main St, New York, NY 10001-1234, USA"), ("New York", "NY"))
        self.assertEqual(source_leads.split_city_state("2 Elm St, Dallas, TX 75201, US"), ("Dallas", "TX"))
        self.assertEqual(source_leads.split_city_state("Chicago, IL"), ("Chicago", "IL"))
        self.assertEqual(source_leads.split_city_state("Somewhere without a state"), (None, None))
        self.assertEqual(source_leads.split_city_state(None), (None, None))


if __name__ == "__main__":
    unittest.main()
