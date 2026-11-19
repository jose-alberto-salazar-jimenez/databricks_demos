"""Helpers for the Metal Surface Defect Diagnostics app.

* classifier_client - calls the image classifier serving endpoint
* severity          - pure severity and human-review rules
* playbook          - reads the defect playbook index through the SQL warehouse
* prompt            - builds the grounded system and user prompts
* llm_client        - calls the Foundation Model API endpoint
"""
