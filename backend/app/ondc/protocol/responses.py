"""Protocol ACK/NACK helpers, independent from existing admin REST errors."""
from typing import Literal
from pydantic import model_validator
from app.ondc.schemas.base import Text, WireModel


class ProtocolError(WireModel):
    type: Literal["CONTEXT-ERROR", "CORE-ERROR", "DOMAIN-ERROR", "JSON-SCHEMA-ERROR"]
    code: Text
    path: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def published_seller_code(self):
        from app.ondc.protocol.specification import seller_error_codes
        if self.code not in seller_error_codes():
            raise ValueError("Error code is not in the pinned official Seller App error list")
        return self


class Ack(WireModel):
    status: Literal["ACK", "NACK"]


class AckMessage(WireModel):
    ack: Ack


class ProtocolResponse(WireModel):
    message: AckMessage
    error: ProtocolError | None = None

    @model_validator(mode="after")
    def coherent_response(self):
        if (self.message.ack.status == "NACK") != (self.error is not None):
            raise ValueError("NACK requires an error; ACK cannot contain an error")
        return self


def ack() -> dict:
    return ProtocolResponse(message=AckMessage(ack=Ack(status="ACK"))).to_wire()


def nack(error: ProtocolError) -> dict:
    return ProtocolResponse(message=AckMessage(ack=Ack(status="NACK")), error=error).to_wire()
