import typing
from typing import Text, Dict, List, Any

from rasa_sdk import Action
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Tracker

if typing.TYPE_CHECKING:  # pragma: no cover
    from rasa_sdk.types import DomainDict

SLOT_OBJECTS_IN_SAMPLE = "objects_in_sample"

class ActionResetObjInSample(Action):

    def name(self) -> Text:
        return "action_reset_objects_in_sample"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: "DomainDict",
    ) -> List[Dict[Text, Any]]:

        slots = [
            SlotSet(SLOT_OBJECTS_IN_SAMPLE, None),
        ]

        return slots
