import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

USER_ID = "pg-test-ee614ebd-aec6-462f-ba1c-0399d74feadd"

result = composio.tools.execute(
    slug="GMAIL_CREATE_EMAIL_DRAFT",
    user_id=USER_ID,
    version="20260702_01",
    arguments={
        "recipient_email": "aijobscout@gmail.com",
        "subject": "Composio proof of life",
        "body": "If you're reading this in your Drafts folder, Composio works.",
    },
)
print(result)
