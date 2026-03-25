def generate_reply(user_id, text, history, state):
    """
    user_id: int
    text: str
    history: list[dict]  # [{"role": "user"/"assistant", "content": "..."}]
    state: dict

    return:
        reply: str
        new_state: dict
    """

    if state is None:
        state = {}

    # пример простой логики
    if "привет" in text.lower():
        reply = "Здравствуйте! Я помогу с бронированием. Что именно хотите забронировать?"
    else:
        reply = f"Вы написали: {text}, у вас в истории уже {len(history)} сообщений."

    return reply, state