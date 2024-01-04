import typing
import random
from typing import Text, Dict, List, Any

from rasa_sdk import Action
from rasa_sdk.events import SlotSet
from rasa_sdk.knowledge_base.utils import (
    SLOT_OBJECT_TYPE,
    SLOT_LAST_OBJECT_TYPE,
    SLOT_ATTRIBUTE,
    reset_attribute_slots,
    SLOT_MENTION,
    SLOT_LAST_OBJECT,
    SLOT_LISTED_OBJECTS,
    get_object_name,
    get_attribute_slots,
)
from rasa_sdk import utils
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Tracker
from rasa_sdk.knowledge_base.storage import InMemoryKnowledgeBase
from rasa_sdk.knowledge_base.storage import KnowledgeBase

if typing.TYPE_CHECKING:  # pragma: no cover
    from rasa_sdk.types import DomainDict

SLOT_OBJECTS_IN_SAMPLE = "objects_in_sample"
SLOT_M_SELECTED = "m_selected"

cmd_ADD = "_add_"
cmd_DELETE = "_delete_"
cmd_CLEAR = "_clear_"
cmd_LIST = "_list_"

m_Limit = 10

class ActionQueryKnowledgeBaseEx(Action):

    def __init__(self):
        # Загружаем базу знаний
        self.knowledge_base = InMemoryKnowledgeBase("knowledge_db.json")
        self.use_last_object_mention = True
        self.count_obj = 7
        self.num_objects = 0

        # перезаписать функции (по умолчанию) представления объекта, 
        # функция представления — это просто имя объекта
        self.knowledge_base.set_representation_function_of_object(
            "workshops", lambda obj: obj["name"] + " (" + obj["direction"] + ")"
        )
        self.knowledge_base.set_representation_function_of_object(
            "directions", lambda obj: obj["name"]
        )
        self.knowledge_base.set_representation_function_of_object(
            "categories", lambda obj: obj["name"]
        )
        self.knowledge_base.set_representation_function_of_object(
            "types", lambda obj: obj["name"]
        )

    def name(self) -> Text:
        return "action_query_knowledge_base"

    def utter_attribute_value(
        self,
        dispatcher: CollectingDispatcher,
        object_name: Text,
        attribute_name: Text,
        attribute_value: Text,
    ):
        """
        Формирует ответ, который информирует пользователя о значении интересующего атрибута.

        Аргументы:
            dispatcher: диспетчер
            object_name: название объекта
            attribute_name: имя атрибута
            attribute_value: значение атрибута
        """

        if attribute_value:
            dispatcher.utter_message(
                text=(
                    f"{attribute_value}"
                )
            )
            # text=f"'{object_name}' has the value '{attribute_value}' for attribute '{attribute_name}'."
        else:
            dispatcher.utter_message(
                text=(
                    f"Не найдено допустимое значение атрибута '{attribute_name}' "
                    f"для объекта '{object_name}'"
                )
            )

    async def utter_objects(
        self,
        dispatcher: CollectingDispatcher,
        object_type: Text,
        objects: List[Dict[Text, Any]]
    ):
        """
        Формирует ответ пользователю, в котором перечисляются все найденные объекты.

        Аргументы:
            dispatcher: диспетчер
            object_type: тип объекта
            objects: список объектов
        """
        if objects:
            """
            dispatcher.utter_message(
                text=f"Обнаружены следующие объекты типа '{object_type}':"
            )
            """

            repr_function = await utils.call_potential_coroutine(
                self.knowledge_base.get_representation_function_of_object(object_type)
            )

            for i, obj in enumerate(objects, 1):
                dispatcher.utter_message(text=f"{i}: {repr_function(obj)}")
            dispatcher.utter_message(text=f"   ({len(objects)} из {self.num_objects})")    
            
        else:
            dispatcher.utter_message(
                text=f"Не удалось найти объекты типа '{object_type}'"
            )        

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: "DomainDict",
    ) -> List[Dict[Text, Any]]:
        """
        Выполняет это действие. Если пользователь задает вопрос об атрибуте, 
        в базе знаний запрашивается этот атрибут. 
        В противном случае, если в запросе не был обнаружен атрибут или 
        пользователь говорит о новом типе объекта, 
        из базы знаний возвращается несколько объектов запрошенного типа.

        Аргументы:
            dispatcher: the dispatcher
            tracker: the tracker
            domain: the domain

        Возвращает: list of slots
        """
        object_type = tracker.get_slot(SLOT_OBJECT_TYPE)
        last_object_type = tracker.get_slot(SLOT_LAST_OBJECT_TYPE)
        attribute = tracker.get_slot(SLOT_ATTRIBUTE)

        new_request = object_type != last_object_type

        if attribute and (attribute == cmd_LIST or attribute == cmd_DELETE or attribute == cmd_CLEAR):
            new_request = False

        if not object_type:
            dispatcher.utter_message(response="utter_ask_rephrase")
            return [SlotSet(SLOT_MENTION, None), SlotSet(SLOT_ATTRIBUTE, None)]

        if not attribute or new_request:
            return await self._query_objects(dispatcher, object_type, tracker)
        elif attribute:
            return await self._query_attribute(
                dispatcher, object_type, attribute, tracker
            )

        dispatcher.utter_message(response="utter_ask_rephrase")
        return []

    async def _get_objects(
        self, object_type: Text, attributes: List[Dict[Text, Text]], limit: int = 5
    ) -> List[Dict[Text, Any]]:
        if object_type not in self.knowledge_base.data:
            return []

        objects = self.knowledge_base.data[object_type]

        # фильтрация объектов по атрибутам
        if attributes:
            objects = list(
                filter(
                    lambda obj: [
                        obj[a["name"]] == a["value"] for a in attributes
                    ].count(False)
                    == 0,
                    objects,
                )
            )

        self.num_objects = len(objects)
        random.shuffle(objects)

        return objects[:limit]

    async def _query_objects(
        self, dispatcher: CollectingDispatcher, object_type: Text, tracker: Tracker
    ) -> List[Dict]:

        # получить количество объектов в выборке
        objects_in_sample = tracker.get_slot(SLOT_OBJECTS_IN_SAMPLE)
        if objects_in_sample:
            self.count_obj = int(objects_in_sample)
            if self.count_obj < 1:
                self.count_obj = 1
            if self.count_obj > 10:
                self.count_obj = 10

        object_attributes = await utils.call_potential_coroutine(
            self.knowledge_base.get_attributes_of_object(object_type)
        )

        # получить все установленные слоты атрибутов типа объекта, чтобы иметь возможность фильтровать список объектов
        attributes = get_attribute_slots(tracker, object_attributes)

        # запросить базу знаний
        objects = await utils.call_potential_coroutine(
            self._get_objects(object_type, attributes, self.count_obj)
        )

        await utils.call_potential_coroutine(
            self.utter_objects(dispatcher, object_type, objects)
        )

        if not objects:
            return reset_attribute_slots(tracker, object_attributes)

        key_attribute = await utils.call_potential_coroutine(
            self.knowledge_base.get_key_attribute_of_object(object_type)
        )

        last_object = None if len(objects) > 1 else objects[0][key_attribute]

        slots = [
            SlotSet(SLOT_OBJECT_TYPE, object_type),
            SlotSet(SLOT_MENTION, None),
            SlotSet(SLOT_ATTRIBUTE, None),
            SlotSet(SLOT_LAST_OBJECT, last_object),
            SlotSet(SLOT_LAST_OBJECT_TYPE, object_type),
            SlotSet(
                SLOT_LISTED_OBJECTS, list(map(lambda e: e[key_attribute], objects))
            ),
        ]

        return slots + reset_attribute_slots(tracker, object_attributes)

    async def _query_attribute(
        self,
        dispatcher: CollectingDispatcher,
        object_type: Text,
        attribute: Text,
        tracker: Tracker,
    ) -> List[Dict]:

        m_selected = tracker.get_slot(SLOT_M_SELECTED)
        if not m_selected:
            m_selected = []

        if attribute == cmd_LIST:
            if len(m_selected) > 0:
                object_repr_func = await utils.call_potential_coroutine(
                    self.knowledge_base.get_representation_function_of_object(object_type)
                )

                dispatcher.utter_message(text=(f"Вы выбрали мастер-классы:"))
                for i, obj in enumerate(m_selected, 1):
                    object_of_interest = await utils.call_potential_coroutine(
                        self.knowledge_base.get_object(object_type, obj)
                    )
                    dispatcher.utter_message(text=f"{i}: {object_repr_func(object_of_interest)}")
            else:
                dispatcher.utter_message(text=(f"Вы еще не записались ни на один мастер-класс"))

            slots = [
                SlotSet(SLOT_OBJECT_TYPE, object_type),
                SlotSet(SLOT_ATTRIBUTE, None),
                SlotSet(SLOT_MENTION, None),
                SlotSet(SLOT_LAST_OBJECT_TYPE, object_type),
                SlotSet(SLOT_M_SELECTED, m_selected),
            ]

            return slots

        elif attribute == cmd_DELETE:
            if len(m_selected) > 0:
                mention_ = tracker.get_slot(SLOT_MENTION)
                if not mention_:
                    dispatcher.utter_message(response="utter_ask_rephrase")
                    return [SlotSet(SLOT_MENTION, None)]

                if mention_ == "LAST":
                    index = -1
                else:
                    index = int(mention_) - 1

                if index >= len(m_selected):
                    dispatcher.utter_message(text=(f"Мастер-класс с указанным номером не найден"))
                else:
                    object_repr_func = await utils.call_potential_coroutine(
                        self.knowledge_base.get_representation_function_of_object(object_type)
                    )
                    object_of_interest = await utils.call_potential_coroutine(
                        self.knowledge_base.get_object(object_type, m_selected[index])
                    )
                    dispatcher.utter_message(text=f"Мастер-класс '{object_repr_func(object_of_interest)}' удален из списка выбранных")
                    m_selected.pop(index)

            else:
                dispatcher.utter_message(text=(f"Вы еще не записались ни на один мастер-класс"))

            slots = [
                SlotSet(SLOT_OBJECT_TYPE, object_type),
                SlotSet(SLOT_ATTRIBUTE, None),
                SlotSet(SLOT_MENTION, None),
                SlotSet(SLOT_LAST_OBJECT_TYPE, object_type),
                SlotSet(SLOT_M_SELECTED, m_selected),
            ]

            return slots

        elif attribute == cmd_CLEAR:
            m_selected.clear()
            dispatcher.utter_message(text=(f"Список выбранных мастер-классов очищен"))

            slots = [
                SlotSet(SLOT_OBJECT_TYPE, object_type),
                SlotSet(SLOT_ATTRIBUTE, None),
                SlotSet(SLOT_MENTION, None),
                SlotSet(SLOT_LAST_OBJECT_TYPE, object_type),
                SlotSet(SLOT_M_SELECTED, m_selected),
            ]

            return slots

        else:
            object_name = get_object_name(
                tracker,
                self.knowledge_base.ordinal_mention_mapping,
                self.use_last_object_mention,
            )

            if not object_name or not attribute:
                dispatcher.utter_message(response="utter_ask_rephrase")
                return [SlotSet(SLOT_MENTION, None)]

            object_of_interest = await utils.call_potential_coroutine(
                self.knowledge_base.get_object(object_type, object_name)
            )

            if attribute != cmd_ADD:
                if not object_of_interest or attribute not in object_of_interest:
                    dispatcher.utter_message(response="utter_ask_rephrase")
                    return [SlotSet(SLOT_MENTION, None)]

            object_repr_func = await utils.call_potential_coroutine(
                self.knowledge_base.get_representation_function_of_object(object_type)
            )

            object_representation = object_repr_func(object_of_interest)

            key_attribute = await utils.call_potential_coroutine(
                self.knowledge_base.get_key_attribute_of_object(object_type)
            )

            object_identifier = object_of_interest[key_attribute]

            if attribute == cmd_ADD:
                if len(m_selected) < m_Limit:
                    if object_identifier in m_selected:
                        dispatcher.utter_message(text=(f"Вы уже записаны на этот мастер-класс"))
                    else:
                        m_selected.append(object_identifier)
                        dispatcher.utter_message(text=(f"Вы записаны на мастер-класс: '{object_representation}'"))
                else:
                    dispatcher.utter_message(text=(f"Вы уже записаны на {m_Limit} мастер-классов, это предел... \nДля устарнения ошибки Вы можете удалить какие-то из выбранных мастер-классов"))
            else:
                value = object_of_interest[attribute]
                await utils.call_potential_coroutine(
                    self.utter_attribute_value(
                        dispatcher, object_representation, attribute, value
                    )
                )

            slots = [
                SlotSet(SLOT_OBJECT_TYPE, object_type),
                SlotSet(SLOT_ATTRIBUTE, None),
                SlotSet(SLOT_MENTION, None),
                SlotSet(SLOT_LAST_OBJECT, object_identifier),
                SlotSet(SLOT_LAST_OBJECT_TYPE, object_type),
                SlotSet(SLOT_M_SELECTED, m_selected),
            ]

            return slots
