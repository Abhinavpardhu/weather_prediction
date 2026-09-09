import json
import os

import requests
from dotenv import load_dotenv
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def home(request):
    """Render the main page with the city search form."""
    return render(request, "weather/index.html")


@csrf_protect
def get_weather(request):
    """Accept a city name, fetch weather, generate a poem with Gemini, and return JSON."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)

    if request.content_type == "application/json":
        try:
            data = json.loads(request.body)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "error": "Please enter a city."}, status=400)
        city = (data.get("city") or "").strip()
    else:
        city = (request.POST.get("city") or "").strip()

    if not city:
        return JsonResponse({"success": False, "error": "Please enter a city."}, status=400)

    if not WEATHER_API_KEY:
        return JsonResponse({"success": False, "error": "Weather API key is missing."}, status=500)

    if not GOOGLE_API_KEY:
        return JsonResponse({"success": False, "error": "Gemini API key is missing."}, status=500)

    try:
        weather_url = "https://api.openweathermap.org/data/2.5/weather"
        weather_params = {
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric",
        }

        weather_response = requests.get(weather_url, params=weather_params, timeout=10)

        if weather_response.status_code == 404:
            return JsonResponse({"success": False, "error": "City not found. Please enter a valid city."}, status=404)

        weather_response.raise_for_status()

        data = weather_response.json()

        city_name = data.get("name", city)
        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})

        temperature = main.get("temp")
        feels_like = main.get("feels_like")
        humidity = main.get("humidity")
        condition = weather.get("description", "Clear").strip().lower()
        wind_speed = wind.get("speed")

        if temperature is None or feels_like is None or humidity is None or wind_speed is None:
            return JsonResponse({"success": False, "error": "Could not fetch complete weather data."}, status=500)

        # Convert wind speed from m/s to km/h.
        wind_speed_kmh = round(float(wind_speed) * 3.6, 1)

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.8,
            google_api_key=GOOGLE_API_KEY,
        )

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a creative poet. Write a beautiful short poem about the current weather. "
                "Follow the user's weather details closely. Keep it poetic and natural. "
                "Write exactly 4 to 6 lines. Match the mood of the weather. Mention the city naturally. "
                "Do not use emojis. Do not explain the poem. Return only the poem.",
            ),
            (
                "user",
                "City: {city}\n"
                "Temperature: {temperature}°C\n"
                "Feels like: {feels_like}°C\n"
                "Weather condition: {condition}\n"
                "Humidity: {humidity}%\n"
                "Wind speed: {wind_speed} km/h\n",
            ),
        ])

        poem_chain = prompt | llm
        poem = poem_chain.invoke(
            {
                "city": city_name,
                "temperature": round(float(temperature), 1),
                "feels_like": round(float(feels_like), 1),
                "condition": condition,
                "humidity": int(humidity),
                "wind_speed": wind_speed_kmh,
            }
        )

        poem_text = getattr(poem, "content", str(poem)).strip()

        return JsonResponse(
            {
                "success": True,
                "weather": {
                    "city": city_name,
                    "temperature": round(float(temperature), 1),
                    "feels_like": round(float(feels_like), 1),
                    "condition": condition,
                    "humidity": int(humidity),
                    "wind_speed": wind_speed_kmh,
                },
                "poem": poem_text,
            },
            status=200,
        )

    except requests.exceptions.RequestException:
        return JsonResponse({"success": False, "error": "Something went wrong. Please try again."}, status=502)
    except ValueError:
        return JsonResponse({"success": False, "error": "Something went wrong. Please try again."}, status=500)
    except Exception:
        return JsonResponse({"success": False, "error": "Something went wrong. Please try again."}, status=500)
