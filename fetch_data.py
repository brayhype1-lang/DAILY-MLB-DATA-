import json
from datetime import datetime
import requests


def get_mlb_data():
  # Fetches current MLB scores/schedule from a free public API
  url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
  response = requests.get(url)
  return response.json()


try:
  data = get_mlb_data()
  output = {
      "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
      "mlb_schedule": data,
  }

  # Save to json file
  with open("daily_mlb_data.json", "w") as f:
    json.dump(output, f, indent=2)

  print("MLB data successfully updated!")
except Exception as e:
  print(f"Error fetching MLB data: {e}")
