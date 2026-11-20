import os
DATABASE = os.getenv("DATABASE_URL", "sqlite:///./raizes.db").replace("sqlite:///", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-before-production-32chars")
