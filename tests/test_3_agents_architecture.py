"""
test_3_agents_architecture.py — Комплексные тесты 3-агентной архитектуры поддержки:
- Агент 1: Инструктор-Аналитик (Grounding, идентичность поддержки, регламентные шаги).
- Агент 2: Диагност-Проводник (интерактивный пошаговый диалог, чек-лист [✓]/[✗], распознавание "не помогло", "ошибка осталась").
- Агент 3: Диспетчер инцидентов и эскалации (генерация № INC-XXXX, строгая маршрутизация L3 -> L2 с подтверждением, Context Card оператора).
"""

import unittest
from unittest.mock import patch
from rag import main_rag
from rag.workflow import handle_workflow, classify_workflow_intent
from rag.escalation import (
    generate_ticket_id,
    determine_support_line,
    format_escalation_reply,
    build_operator_context_card
)


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class MockChat:
    def __init__(self, chat_id=123):
        self.id = chat_id
        self.context_cache = {}
        self.active_workflow = None
        self.current_step = 0
        self.assigned_to = None

    def save(self, update_fields=None):
        pass


class TestThreeAgentsArchitecture(unittest.TestCase):

    def setUp(self):
        self.chat = MockChat(chat_id=999)

    def test_agent3_ticket_and_strict_l3_routing(self):
        """Агент 3: Проверка генерации тикета и обязательной маршрутизации L3 -> L2 с подтверждением."""
        # 1. Генерация тикета
        ticket = generate_ticket_id(12345)
        self.assertTrue(ticket.startswith("INC-"))
        self.assertIn("2026", ticket)

        # 2. Проблема уровня L3 (ошибка 500 / сервер) ДОЛЖНА маршрутизироваться на L2
        line_500 = determine_support_line("Что делать при ошибке 500 на сервере?")
        self.assertEqual(line_500["routed_line"], "L2", "L3-проблема должна направляться на L2!")
        self.assertTrue(line_500["needs_l3_confirmation"], "Должен быть выставлен флаг подтверждения 3-й линии!")
        self.assertIn("3-я линия", line_500["target_specialist"])

        # 3. Формирование ответа пользователю
        reply = format_escalation_reply(ticket, line_500, ["[✗] Шаг 1: Ошибка 500 сохраняется"])
        self.assertIn(ticket, reply)
        self.assertIn("2-ю линию технической поддержки", reply)
        self.assertIn("специалистов 3-й линии", reply)
        self.assertIn("чек-лист диагностики", reply.lower())

        # 4. Формирование Context Card оператора
        card = build_operator_context_card(
            ticket_id=ticket,
            issue="Ошибка 500 на Портале",
            line_info=line_500,
            checkpoints=["[✗] Шаг 1: Проверка в инкогнито — не помогло"],
            error_code="500"
        )
        self.assertEqual(card["ticket_id"], ticket)
        self.assertEqual(card["assigned_line"], "L2")
        self.assertTrue(card["needs_l3_confirmation"])
        self.assertEqual(len(card["checkpoints"]), 1)

    def test_agent2_intent_classification(self):
        """Агент 2: Проверка распознавания живого языка (Успех / Сбой / Уточнение / Отказ)."""
        # Успех / Продвижение (ADVANCE)
        self.assertEqual(classify_workflow_intent("готово"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("сделал"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("дальше"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("следующий шаг"), "ADVANCE")
        self.assertEqual(classify_workflow_intent("получилось"), "ADVANCE")

        # Сбой / Проблема (FAILURE)
        self.assertEqual(classify_workflow_intent("не помогло"), "FAILURE")
        self.assertEqual(classify_workflow_intent("ошибка осталась"), "FAILURE")
        self.assertEqual(classify_workflow_intent("всё равно пишет 500"), "FAILURE")
        self.assertEqual(classify_workflow_intent("выдает ту же ошибку"), "FAILURE")
        self.assertEqual(classify_workflow_intent("нет такой кнопки"), "FAILURE")
        self.assertEqual(classify_workflow_intent("не работает"), "FAILURE")

        # Согласие начать (AFFIRMATIVE)
        self.assertEqual(classify_workflow_intent("давай"), "AFFIRMATIVE")
        self.assertEqual(classify_workflow_intent("давай по шагам"), "AFFIRMATIVE")
        self.assertEqual(classify_workflow_intent("поехали"), "AFFIRMATIVE")

        # Запрос оператора / человека (OPERATOR)
        self.assertEqual(classify_workflow_intent("позови человека"), "OPERATOR")
        self.assertEqual(classify_workflow_intent("оператор"), "OPERATOR")

        # Уточняющий вопрос / Просьба пояснить (CLARIFY)
        self.assertEqual(classify_workflow_intent("раскажи подробнее"), "CLARIFY")
        self.assertEqual(classify_workflow_intent("расскажи подробнее"), "CLARIFY")
        self.assertEqual(classify_workflow_intent("подробнее"), "CLARIFY")
        self.assertEqual(classify_workflow_intent("поясни этот шаг"), "CLARIFY")
        self.assertEqual(classify_workflow_intent("не понял"), "CLARIFY")

    def test_agent2_step_advancement_and_checklist(self):
        """Агент 2: Пошаговое продвижение с сохранением [✓] в чек-лист."""
        self.chat.context_cache = {'suggested_workflow': 'ecp_cryptopro'}
        
        # Шаг 1
        res1 = handle_workflow("Давай", self.chat)
        self.assertIsNotNone(res1)
        self.assertIn("Шаг 1 из", res1["answer"])
        self.assertEqual(self.chat.active_workflow, "ecp_cryptopro")
        self.assertEqual(self.chat.current_step, 1)
        # Проверяем чистое каноническое название статьи в цитате
        self.assertEqual(res1["citations"][0]["title"], "Как произвести настройку плагина КРИПТОПРО?")

        # Шаг 2 (пользователь написал "сделал")
        res2 = handle_workflow("сделал, всё получилось", self.chat)
        self.assertIsNotNone(res2)
        self.assertIn("Шаг 2 из", res2["answer"])
        self.assertEqual(self.chat.current_step, 2)
        
        # Проверяем, что в чек-листе зафиксированы шаги
        checkpoints = self.chat.context_cache.get("checkpoints", [])
        self.assertTrue(any("[✓]" in cp for cp in checkpoints))

    def test_agent2_failure_triggers_agent3_escalation(self):
        """Агент 2 + Агент 3: Если пользователь на шаге сообщает о сбое -> мгновенная эскалация с тикетом."""
        self.chat.active_workflow = "system_error_troubleshooting"
        self.chat.current_step = 1
        self.chat.context_cache = {"suggested_workflow": "system_error_troubleshooting"}

        # Пользователь отвечает нестандартной репликой о сохранении ошибки 500
        res = handle_workflow("попробовал в инкогнито, всё равно пишет 500", self.chat)
        self.assertIsNotNone(res)

        # Проверяем, что сработала эскалация (Агент 3)
        self.assertIn("официально зарегистрировано", res["answer"])
        self.assertIn("INC-2026-", res["answer"])
        self.assertIn("2-ю линию технической поддержки", res["answer"])
        self.assertIn("специалистов 3-й линии", res["answer"])
        
        # Маршрутизация на L2 (не напрямую на L3!)
        self.assertEqual(res["line_info"]["line"], "L2")

        # В карточке оператора зафиксирован чек-лист сбоя
        operator_card = res.get("operator_card")
        self.assertIsNotNone(operator_card)
        self.assertTrue(operator_card["needs_l3_confirmation"])
        self.assertEqual(operator_card["assigned_line"], "L2")
        self.assertTrue(any("[✗]" in cp for cp in operator_card["checkpoints"]))

        # Активный процесс снят, чтобы чат не залипал
        self.assertIsNone(self.chat.active_workflow)

    def test_zmo_and_223fz_knowledge_graph(self):
        """Агент 1: Проверка графового узла по ЗМО и 223-ФЗ со статьей 589954."""
        from rag.graph_rag import find_graph_node
        node = find_graph_node("Закупки малого объема до 3 млн рублей по 223-ФЗ")
        self.assertIsNotNone(node)
        self.assertEqual(node["id"], "zmo_procurement_rules")
        self.assertEqual(node["title"], "Что такое закупки малого объема (ЗМО) на Портале поставщиков?")
        self.assertIn("589954", node["url"])
        self.assertIn("44-ФЗ", str(node["law_references"]))
        self.assertIn("223-ФЗ", str(node["law_references"]))
        self.assertIn("Котировочная сессия", str(node["workflow_steps"]))

    def test_clean_citation_section_and_titles(self):
        """Агент 1/3: Санитария ссылок, удаление технического мусора (Часть N) и SOURCE URL."""
        from rag.url_utils import clean_citation_section, clean_citation_title, normalize_portal_url

        # Очистка мусора чанкера (Часть 12) и SOURCE URL
        sec1 = clean_citation_section("SOURCE URL: https://www.roseltorg.ru/knowledge_db/44fz/notes/test (Часть 5)")
        self.assertEqual(sec1, "")

        sec2 = clean_citation_section("Введение > Прикрепленный регламент/инструкция: (Часть 12)")
        self.assertEqual(sec2, "Введение > Прикрепленный регламент/инструкция")

        # Очистка названий
        title_doc = clean_citation_title("Инструкция_по_созданию_оферты_и_СТЕ.pdf", "https://zakupki.mos.ru/cms/Media/docs/Инструкция_по_созданию_оферты_и_СТЕ.pdf")
        self.assertEqual(title_doc, "Инструкция по созданию оферты и СТЕ")

        # Нормализация ссылки статьи 589954
        url_art = normalize_portal_url("https://zakupki.mos.ru/knowledgebase/article/details/ais/589954")
        self.assertEqual(url_art, "https://zakupki.mos.ru/knowledgebase/article/details/ais/589954")

    def test_fas_and_portal_arbitration_distinction(self):
        """Проверка строгого юридического разделения: ФАС (ЕИС) vs Жалоба на Портале (Арбитраж)."""
        from rag.graph_rag import find_graph_node
        from rag.url_utils import clean_citation_title, normalize_portal_url

        # 1. Запрос по ФАС -> официальный портал ЕИС (zakupki.gov.ru), а не регламент Портала
        node_fas = find_graph_node("Как подать жалобу в ФАС по 44-ФЗ?")
        self.assertIsNotNone(node_fas)
        self.assertEqual(node_fas["id"], "fas_complaint_44fz")
        self.assertEqual(node_fas["url"], "https://zakupki.gov.ru")
        self.assertIn("zakupki.gov.ru", node_fas["channel"])
        title_fas = clean_citation_title(node_fas["title"], node_fas["url"])
        self.assertEqual(title_fas, "Официальный портал ЕИС Закупки (zakupki.gov.ru)")

        # 2. Запрос по блокировке на Портале -> Арбитражная комиссия Портала (статья 507199)
        node_arb = find_graph_node("Как обжаловать блокировку на Портале поставщиков?")
        self.assertIsNotNone(node_arb)
        self.assertEqual(node_arb["id"], "portal_complaint_arbitration")
        self.assertIn("507199", node_arb["url"])
        self.assertEqual(node_arb["title"], "Как обжаловать блокировку на Портале поставщиков?")
        self.assertIn("Арбитраж", str(node_arb["law_references"]))

        # 3. Точные названия приложений Регламента CMS
        cms_app8_url = "https://zakupki.mos.ru/knowledgebase/article/details/cms/4n50757tk43h15gxn22r5655d9"
        title_app8 = clean_citation_title("Общий регламент", cms_app8_url)
        self.assertEqual(title_app8, "Приложение 8. Правила блокировки личного кабинета и ее снятия")

        cms_app4_url = "https://zakupki.mos.ru/knowledgebase/article/details/cms/4gtfe46htq9ar7804w2j8g5gcy"
        title_app4 = clean_citation_title("Что-то", cms_app4_url)
        self.assertEqual(title_app4, "Приложение 4. Правила проведения котировочной сессии")

        # 4. Общая ссылка на Регламент не может называться "Подача жалобы в ФАС"
        reg_url = "https://zakupki.mos.ru/knowledgebase/article/regulation/cms"
        title_reg = clean_citation_title("Подача жалобы в ФАС", reg_url)
        self.assertEqual(title_reg, "Регламент информационного взаимодействия АИС «Портал поставщиков»")

    def test_workflow_clarification_and_continuation(self):
        """Проверка: уточнение на шаге регламента ('раскажи подробнее') не сбрасывает процесс и дает верную цитату."""
        self.chat.active_workflow = "zmo_procurement_rules"
        self.chat.current_step = 3
        self.chat.context_cache = {"suggested_workflow": "zmo_procurement_rules"}

        # 1. Пользователь на шаге 3 пишет "раскажи подробнее"
        intent = classify_workflow_intent("раскажи подробнее", active=True)
        self.assertEqual(intent, "CLARIFY")

        # handle_workflow передает управление в RAG без сброса активного workflow
        wf_res = handle_workflow("раскажи подробнее", self.chat)
        self.assertIsNone(wf_res)
        self.assertEqual(self.chat.active_workflow, "zmo_procurement_rules")
        self.assertEqual(self.chat.current_step, 3)

        # 2. После получения ответа пользователь пишет "далее"
        intent_next = classify_workflow_intent("далее", active=True)
        self.assertEqual(intent_next, "ADVANCE")

        # handle_workflow продвигает на шаг 4
        wf_next = handle_workflow("далее", self.chat)
        self.assertIsNotNone(wf_next)
        self.assertIn("Шаг 4 из 5", wf_next["answer"])
        self.assertEqual(self.chat.current_step, 4)

        # 3. Название статьи в цитатах пошагового регламента строго каноническое
        self.assertEqual(len(wf_next["citations"]), 1)
        self.assertEqual(wf_next["citations"][0]["title"], "Что такое закупки малого объема (ЗМО) на Портале поставщиков?")
        self.assertIn("589954", wf_next["citations"][0]["url"])

    def test_out_of_kb_portal_query_triggers_agent3_escalation(self):
        """Проверка кейса 'Банан': сущность отсутствует в БЗ Портала -> мгновенная эскалация с тикетом и БЕЗ ложных цитат."""
        from rag.main_rag import rag_pipeline_result

        class MockHit:
            def __init__(self, title, section_header, text, score=0.25, url="https://zakupki.mos.ru/knowledgebase/article/details/ais/507178"):
                self.score = score
                self.payload = {
                    "title": title,
                    "section_header": section_header,
                    "text": text,
                    "url": url,
                    "images": []
                }

        # Имитируем ситуацию, когда семантический поиск вернул нерелевантную статью о блокировке поставщика
        mock_hits = [
            MockHit(
                title="Если поставщик заблокирован на Портале поставщиков, будет ли он внесен в реестр недобросовестных поставщиков?",
                section_header="Блокировка",
                text="Информация о блокировке учетной записи поставщика на Портале поставщиков Москвы.",
                score=0.25
            )
        ]

        with patch("rag.search.search_hybrid", return_value=mock_hits), \
             patch("rag.main_rag._call_local_gpt", return_value="ON_TOPIC"):
            res = rag_pipeline_result(
                "что такое банан и будет ли он продаваться на портале поставщиков",
                chat=self.chat
            )

        # 1. Ответ содержит официальную регистрацию обращения (тикет)
        self.assertIn("официально зарегистрировано", res["answer"])
        self.assertIn("INC-2026-", res["answer"])
        self.assertIn("1-й линии общей поддержки", res["answer"])
        self.assertIn("нет регламентированной информации", res["answer"])

        # 2. Ложные цитаты (статья о блокировке) ПОЛНОСТЬЮ исключены
        self.assertEqual(res["citations"], [], "Для вопроса вне базы знаний цитаты должны быть пустыми!")

        # 3. Карточка оператора сформирована
        card = res.get("operator_card")
        self.assertIsNotNone(card)
        self.assertEqual(card["assigned_line"], "L1")
        self.assertIn("банан", card["issue"])

        # 4. Чат назначен на сотрудника
        self.assertEqual(self.chat.assigned_to, "support_staff")

    def test_pure_off_topic_polite_refusal(self):
        """Проверка чистого оффтопика ('как испечь пирог'): вежливый отказ без ложных цитат и без тикета."""
        from rag.main_rag import rag_pipeline_result

        with patch("rag.main_rag._call_local_gpt", return_value="OFF_TOPIC"):
            res = rag_pipeline_result(
                "как испечь яблочный пирог",
                chat=self.chat
            )

        self.assertEqual(res["citations"], [])
        self.assertIn("другой сфере", res["answer"])
        # Тикет не создается при оффтопике
        self.assertNotIn("INC-2026-", res["answer"])

    def test_pdf_citation_extraction_and_linking(self):
        """Проверка извлечения прямых ссылок на официальные PDF-инструкции из метаданных чанка."""
        from rag.url_utils import extract_pdf_citation, clean_citation_section

        # 1. Тестируем прямое извлечение из percent-encoded section_header
        sec_encoded = "Введение > Содержимое документа (%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F_%D0%BF%D0%BE_%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B0%D1%86%D0%B8%D0%B8_%D0%BD%D0%B0_%D0%9F%D0%BE%D1%80%D1%82%D0%B0%D0%BB%D0%B5.pdf): (Часть 1)"
        pdf_cit = extract_pdf_citation(sec_encoded)
        self.assertIsNotNone(pdf_cit)
        self.assertEqual(pdf_cit["title"], "Инструкция по регистрации на Портале")
        self.assertIn("https://zakupki.mos.ru/cms/Media/docs/", pdf_cit["url"])
        self.assertIn("%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F", pdf_cit["url"])
        self.assertEqual(pdf_cit["section"], "Официальный документ (PDF)")

        # 2. Тестируем очистку section_header
        clean_sec = clean_citation_section(sec_encoded)
        self.assertEqual(clean_sec, "Введение > Инструкция по регистрации на Портале")


if __name__ == '__main__':
    unittest.main()


