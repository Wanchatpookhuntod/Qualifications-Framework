import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore


_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """Return a singleton Firestore client.

    Uses GOOGLE_APPLICATION_CREDENTIALS if set, otherwise defaults to the service
    account JSON committed under instance/.
    """
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        cred_path = os.path.join(
            os.path.dirname(__file__),
            "instance",
            "qualificationsframework-34219c0bd960.json",
        )

    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Firestore credentials not found at {cred_path}. Set GOOGLE_APPLICATION_CREDENTIALS."
        )

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))

    _firestore_client = firestore.client()
    return _firestore_client
