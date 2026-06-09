def extract_event(payload):
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        message_type = message.get("type", "")
        if not message_type:
            if "text" in message:
                message_type = "text"
            elif "image" in message:
                message_type = "image"

        event = {
            "phone": message["from"],
            "message_id": message.get("id", ""),
            "type": message_type,
            "text": "",
            "media_id": "",
            "mime_type": "",
            "sha256": "",
            "caption": "",
        }
        if event["type"] == "text":
            event["text"] = message.get("text", {}).get("body", "")
        elif event["type"] == "image":
            image = message.get("image", {})
            event.update(
                {
                    "media_id": image.get("id", ""),
                    "mime_type": image.get("mime_type", ""),
                    "sha256": image.get("sha256", ""),
                    "caption": image.get("caption", ""),
                }
            )
        return event
    except (KeyError, IndexError, TypeError):
        return None


def extract_message(payload):
    event = extract_event(payload)
    if not event:
        return None, None
    return event["phone"], event["text"]
