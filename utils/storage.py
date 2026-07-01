import os
import json
def load_user(email: str) -> dict | None:
    if not os.path.exists("users.json"):
        return None
    with open("users.json", "r") as f:
        content = f.read()
        if not content.strip():
            return None
        data = json.loads(content)

    return data["users"].get(email, None)
def save_user(email:str,profile: dict) -> None:
    if os.path.exists("users.json"):
        with open("users.json","r") as f:
            data = json.load(f)
    else:
        data = {"users":{}}
    data["users"][email] = profile
    with open("users.json",'w') as f:
        json.dump(data,f)


if __name__ == "__main__":
    save_user("nikhil", {"goal": "lose_fat", "weight_kg": 75})
    print(load_user("nikhil"))
    print(load_user("unknown"))
