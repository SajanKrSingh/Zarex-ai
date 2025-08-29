# services/weather.py
import requests
import logging

logger = logging.getLogger(__name__)

def get_weather(city: str, api_key: str) -> str:
    """Fetches weather data for a city and formats it into a readable string."""
    if not api_key:
        return "Weather API key is not configured. Please add it in the settings."

    base_url = "http://api.weatherapi.com/v1/current.json"
    params = {
        "key": api_key,
        "q": city,
        "aqi": "no"
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        location = data["location"]["name"]
        temp_c = data["current"]["temp_c"]
        condition = data["current"]["condition"]["text"]

        return f"The current weather in {location} is {temp_c} degrees Celsius with {condition}."

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather data: {e}")
        return "Sorry, I couldn't fetch the weather information at the moment."
    except KeyError:
        return f"Sorry, I couldn't find the weather for {city}. Please try another location."
