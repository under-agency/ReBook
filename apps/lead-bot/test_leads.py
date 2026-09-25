from leads import CITIES, WRITE_HERE, Lead, answer, notify_html, start


def test_full_flow_from_tier_button():
    lead, reply = start("tier_4900")
    assert "Как вас зовут" in reply.text
    assert answer(lead, "Анна").text == "Как называется ваш салон?"
    reply = answer(lead, "Студия «Ногти»")
    assert reply.buttons == list(CITIES)
    reply = answer(lead, "Казань")
    assert reply.ask_phone and WRITE_HERE in reply.buttons
    reply = answer(lead, phone="+79000000001")
    assert reply.done
    assert (lead.name, lead.salon, lead.city, lead.contact) == (
        "Анна", "Студия «Ногти»", "Казань", "+79000000001")
    assert "Старт" in lead.source


def test_avito_link_already_knows_the_city():
    lead, _ = start("avito_tmn")
    answer(lead, "Анна")
    reply = answer(lead, "Салон")
    assert reply.ask_phone, "город известен из ссылки — сразу спрашиваем контакт"
    assert (lead.city, lead.source) == ("Тюмень", "Avito")


def test_empty_answer_repeats_the_question():
    lead, _ = start(None)
    assert answer(lead, "   ").text == "Как вас зовут?"
    assert lead.name is None
    answer(lead, "Анна")
    assert answer(lead, "").text == "Как называется ваш салон?"
    assert lead.salon is None


def test_write_here_means_telegram():
    lead, _ = start("landing")
    for text in ("Анна", "Салон", "Тюмень"):
        answer(lead, text)
    assert answer(lead, WRITE_HERE).done
    assert lead.contact == "Telegram"


def test_typed_contact_is_accepted():
    lead, _ = start("landing")
    for text in ("Анна", "Салон", "Тюмень", "звоните после 18"):
        reply = answer(lead, text)
    assert reply.done and lead.contact == "звоните после 18"


def test_long_input_is_trimmed_and_spaces_collapsed():
    lead, _ = start(None)
    answer(lead, "  Анна   Петровна  ")
    assert lead.name == "Анна Петровна"
    lead, _ = start(None)
    answer(lead, "А" * 500)
    assert len(lead.name) == 100


def test_source_labels():
    assert start("tier_9900")[0].source.endswith("9 900 ₽")
    assert "chat_salons" in start("chat_salons")[0].source
    assert start(None)[0].source == "без метки"
    assert len(start("x" * 200)[0].source) < 50


def test_notification_escapes_user_input():
    lead = Lead(source="лендинг", city="Казань", name="<b>Анна</b>", salon="A & B",
                contact="+79000000001")
    html = notify_html(lead, 42, None)
    assert "&lt;b&gt;Анна&lt;/b&gt;" in html
    assert "A &amp; B" in html
    assert 'href="tg://user?id=42"' in html


def test_notification_prefers_username():
    lead = Lead(source="Avito", city="Тюмень", name="Анна", salon="Салон", contact="Telegram")
    html = notify_html(lead, 42, "example_user")
    assert "@example_user" in html and "tg://user" not in html
    assert "Откуда: Avito" in html
