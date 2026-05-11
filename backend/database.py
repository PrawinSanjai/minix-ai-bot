from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from config import Configuration

config = Configuration()


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)
base = declarative_base(metadata=metadata)
engine = create_engine(url=config.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=0)
db_session = sessionmaker(autocommit=False, expire_on_commit=False, autoflush=True, bind=engine)

@contextmanager
def get_db():
    """
    Create database session for database operations.
    """
    try:
        db = db_session()
        yield db
        db.commit()
    except Exception as e:
        print(f"Exception occured while connectinng with DB {str(e)}")
        db.rollback()
        raise e
    finally:
        db.close()