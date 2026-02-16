from sqlalchemy.orm import Session

from app.services.personal_pipeline import PersonalPipeline
from app.services.company_pipeline import CompanyPipeline
from app.models.user import User


class PipelineFactory:
    @staticmethod
    def get_pipeline(user: User, db: Session):
        if user.account_type == "company":
            return CompanyPipeline(db=db, user=user)

        # default → personal
        return PersonalPipeline(db=db, user=user)
