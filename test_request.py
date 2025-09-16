import requests, json

url = "http://localhost:8001/generate-mcqs"
files = {"file": open("Test.pdf", "rb")}
data = {"num_questions": 5}

resp = requests.post(url, files=files, data=data)
print(json.dumps(resp.json(), indent=2))
