"""Role-based access control constants for API endpoints."""

# Every valid role in the system (used for validation)
ALL_ROLES = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]

# All authenticated tenant users (read-only baseline)
READ_ROLES = ["analyst", "sector_lead", "pm", "faculty", "trustee", "admin"]

# Research upload and semantic search
RESEARCH_ROLES = ["analyst", "sector_lead", "pm", "admin"]

# Portfolio creation
PORTFOLIO_WRITE_ROLES = ["pm", "admin"]

# Holdings updates
HOLDINGS_WRITE_ROLES = ["pm", "sector_lead", "admin"]

# Compliance evaluation and violation reads
COMPLIANCE_ROLES = ["analyst", "sector_lead", "pm", "admin"]

# What-if simulation (no DB writes)
SIMULATION_ROLES = ["pm", "sector_lead", "admin"]

# Institution provisioning
ADMIN_ROLES = ["admin"]
