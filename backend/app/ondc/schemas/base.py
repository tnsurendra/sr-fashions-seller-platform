from typing import Annotated
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from app.ondc.utils.validation import http_url, timestamp, positive_duration

Text = Annotated[str, StringConstraints(min_length=1)]
HttpUrl = Annotated[Text, AfterValidator(http_url)]
Timestamp = Annotated[Text, AfterValidator(timestamp)]
Duration = Annotated[Text, AfterValidator(positive_duration)]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    def to_wire(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
