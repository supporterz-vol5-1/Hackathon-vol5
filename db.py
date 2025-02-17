import hashlib
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Literal, NoReturn, Optional, Union

import sqlalchemy
from sqlalchemy.engine.base import Engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session

from models import User, Work, WorkTime


def create_engine(
    dialect: str,
    password: str,
    host: str,
    username: str,
    port: Union[str, int],
    dbname: str,
    driver: str = "",
    echo: Optional[Union[bool, Literal["debug"]]] = None,
) -> Engine:
    if driver != "":
        driver = "+" + driver
    url = f"{dialect}{driver}://{username}:{password}@{host}:{port}/{dbname}"
    if dialect == "sqlite":
        url = f"sqlite:///{str(Path(dbname).resolve())}"
    else:
        # if specify postgresql, port must be int
        assert type(port) == int
    return sqlalchemy.create_engine(url, echo=echo)


def initialize(engine: Engine) -> None:
    # Base.metadata.drop_all(bind=engine)
    # Base.metadata.create_all(bind=engine)
    for table in (User, Work, WorkTime):
        try:
            table.__table__.drop(bind=engine)
        except Exception:
            pass
        table.__table__.create(bind=engine)


def create_session(engine: Engine) -> Session:
    return sessionmaker(bind=engine)()


def is_valid_user(engine: Engine, user_name: str, token: str) -> NoReturn:
    session = create_session(engine)
    is_exists = bool(session.query(User).filter(User.name == user_name).first())
    if not is_exists:
        session.close()
        raise UserNotFoundError
    is_valid_token = bool(
        session.query(User).filter(User.name == user_name, User.token == token).first())

    if not is_valid_token:
        session.close()
        raise InvalidTokenError


def update(
    engine: Engine,
    user_name: str,
    request_body: Dict[str, str],
    day=date,
) -> None:
    is_valid_user(engine, user_name, request_body.get("token", ""))
    # DO NOT USE THIS !!!!
    session = create_session(engine)
    # is_valid = bool(session.query(User).filter(User.name == user_name).first())
    # if not is_valid:
    #     raise UserNotFoundError
    # is_valid = bool(
    #     session.query(User).filter(User.name == user_name,
    #                                User.token == request_body["token"]).first())
    # if not is_valid:
    #     raise InvalidTokenError

    registerd_data = (session.query(WorkTime).filter(
        WorkTime.user_name == user_name,
        WorkTime.filetype == request_body["filetype"],
    ).first())

    if registerd_data:
        registerd_data.work_time = registerd_data.work_time + request_body["work_time"]
    else:
        work_time = WorkTime(
            user_name=user_name,
            filetype=request_body["filetype"],
            work_time=request_body["work_time"],
            day=day,
        )
        session.add(work_time)

    session.commit()
    session.close()


class UserNotFoundError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def register_user(engine: Engine, user_name: str) -> Optional[str]:
    session = create_session(engine)
    if session.query(User).filter(User.name == user_name).first():
        return None
    else:
        now = datetime.now().strftime("%y%m%d%H%M%S")
        s = list(user_name + now)
        random.shuffle(s)
        shuffled = "".join(s)
        hashed = hashlib.md5(shuffled.encode()).hexdigest()
        user = User(name=user_name, token=hashed)
        session.add(user)
        session.commit()
        session.close()
        return hashed


def get_recent_week(engine: Engine, user_name: str) -> Optional[List[Dict[str, float]]]:
    session = create_session(engine)
    one_week_ago = date.today() - timedelta(days=7)
    if session.query(User).filter(User.name == user_name).first():
        seven_days: List[Dict[str, float]] = [{} for _ in range(7)]
        data = (session.query(WorkTime).filter(
            WorkTime.user_name == user_name,
            WorkTime.day >= one_week_ago,
            WorkTime.day < date.today(),
        ).order_by(WorkTime.day)).all()
        if data:
            for d in data:
                seven_days[(d.day - one_week_ago).days][d.filetype] = d.work_time
        return seven_days
    else:
        return None


def start_written(
    engine: Engine,
    user_name: str,
    now: datetime,
    request_body: Dict[str, str],
) -> None:
    is_valid_user(engine, user_name, request_body.get("token", ""))
    # Every human can write only one file at once
    session = create_session(engine)
    is_start = (session.query(Work).filter(
        Work.user_name == user_name, Work.filetype == request_body["filetype"]).first())
    # is_start = (session.query(Work).filter(Work.user_name == user_name).first())
    if is_start:
        # close old work
        work_time = (now - is_start.start).total_seconds()
        # TODO 最大時間の設定
        # if work_time <= ????:
        worked = WorkTime(
            user_name=is_start.user_name,
            filetype=is_start.filetype,
            work_time=work_time,
            day=date.today(),    # 終了した日付で登録される
        )
        session.delete(is_start)
        session.add(worked)
        session.commit()
        return None
    else:
        work = Work(user_name=user_name, filetype=request_body["filetype"], start=now)
        session.add(work)
        session.commit()
        session.close()
        return None


def stop_written(
    engine: Engine,
    user_name: str,
    now: datetime,
    request_body: Dict[str, str],
) -> None:
    is_valid_user(engine, user_name, request_body.get("token", ""))
    session = create_session(engine)
    is_start = (session.query(Work).filter(
        Work.user_name == user_name, Work.filetype == request_body["filetype"]).first())
    # is_start = (session.query(Work).filter(Work.user_name == user_name).first())
    if is_start:
        work_time = (now - is_start.start).total_seconds()
        worked = WorkTime(
            user_name=is_start.user_name,
            filetype=is_start.filetype,
            work_time=work_time,
            day=date.today(),
        )
        session.delete(is_start)
        session.add(worked)
        session.commit()
        return None
    else:
        return None
