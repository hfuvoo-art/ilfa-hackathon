from hashlib import sha1


def make_patient_id(last_name: str, first_name: str) -> str:
    last_name = last_name.strip().lower().replace("ё", "е")
    first_name = first_name.strip().lower().replace("ё", "е")
    key = f"{last_name}|{first_name}"
    return sha1(key.encode("utf-8")).hexdigest()[:12]