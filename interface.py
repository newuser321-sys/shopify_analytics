import requests

# Ask user for inputs
question = input("Enter your question: ")
store_id = input("Enter the store ID: ")

# sample: question = "how many snowboards do i have?"

# Local gateway server URL
url = "http://localhost:8000/api/v1/questions"

# Prepare data payload
payload = {
    "question": question,
    "store_id": store_id
}

try:
    # Send POST request
    response = requests.post(url, json=payload)
    # Check response
    if response.status_code == 200:
        print("Server response:", response.json())
    else:
        print(f"Backend Error. Status code: {response.status_code}")
        print("Response:", response.json())
except requests.exceptions.RequestException as e:
    print("Error connecting to gateway server:\n", e)


