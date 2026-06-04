import glob
import os
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore


_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """Return a singleton Firestore client.

    Priority:
    1. GOOGLE_APPLICATION_CREDENTIALS env var (local dev / explicit key file)
    2. Application Default Credentials (Cloud Run, GCE, etc.)
    3. Fallback to instance/ JSON file for local development
    """
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if cred_path and os.path.exists(cred_path):
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        else:
            # Prefer local instance/ JSON (dev), fall back to ADC (Cloud Run)
            matches = glob.glob(
                os.path.join(os.path.dirname(__file__), "instance", "qualificationsframework-*.json")
            )
            if matches:
                firebase_admin.initialize_app(credentials.Certificate(matches[0]))
            else:
                firebase_admin.initialize_app(credentials.ApplicationDefault())

    _firestore_client = firestore.client()
    return _firestore_client
