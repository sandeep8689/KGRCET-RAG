
import requests

url = "https://kgr.ac.in/robots.txt"

try:
    response = requests.get(url, timeout=20)

    print("Status code:", response.status_code)
    print("Final URL:", response.url)
    print("Content type:", response.headers.get("Content-Type"))
    print("Robots.txt contents:")
    print(response.text[:10000])

except requests.RequestException as error:
    print("Could not access robots.txt:", error)
