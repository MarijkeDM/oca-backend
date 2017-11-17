# -*- coding: utf-8 -*-
# Copyright 2017 Mobicage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @@license_version:1.2@@

from rogerthat.rpc import users
from rogerthat.settings import get_server_settings
from rogerthat.to import ReturnStatusTO
from rogerthat.utils import now, send_mail
from google.appengine.ext import db
from mcfw.restapi import rest
from mcfw.rpc import arguments, returns
from shop.models import RegioManagerTeam
from solutions import translate
from solutions.common import SOLUTION_COMMON
from solutions.common.bizz.qanda import search_question as bizz_search_question
from solutions.common.dal import get_solution_settings
from solutions.common.models.qanda import Question, QuestionReply
from solutions.common.to.qanda import QuestionTO, QuestionsWithCursorReturnStatusTO
from solution_server_settings import get_solution_server_settings

@rest("/common/qanda/search", "get", read_only_access=True)
@returns(QuestionsWithCursorReturnStatusTO)
@arguments(search_string=unicode, count=(int, long), cursor=unicode)
def search_question(search_string, count, cursor=None):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    questions, cursor = bizz_search_question(sln_settings.main_language, search_string, count, cursor)
    return QuestionsWithCursorReturnStatusTO.create(True, None, [QuestionTO.fromModel(q, False, sln_settings) for q in questions], cursor)

@rest("/common/qanda/ask", "post")
@returns()
@arguments(title=unicode, description=unicode, modules=[unicode])
def ask_question(title, description, modules):
    solution_server_settings = get_solution_server_settings()
    default_team_id = RegioManagerTeam.get_mobicage().id
    def trans():
        sln_settings = get_solution_settings(users.get_current_user())

        Question(author=users.get_current_user(),
                 timestamp=now(),
                 title=title,
                 description=description,
                 modules=modules,
                 language=sln_settings.main_language,
                 team_id=default_team_id).put()
        
        message = """Please reply to %s (%s) with the following link:
%s/internal/shop/questions

Title:
%s

Description:
%s""" % (sln_settings.login.email() if sln_settings.login else "", users.get_current_user(),
         get_server_settings().baseUrl, title, description)
        send_mail(get_server_settings().senderEmail, solution_server_settings.solution_qanda_info_receivers, title,
                  message, transactional=True)

    xg_on = db.create_transaction_options(xg=True)
    db.run_in_transaction_options(xg_on, trans)

@rest("/common/qanda/reply", "post")
@returns(ReturnStatusTO)
@arguments(question_id=(int, long), description=unicode)
def reply_on_question(question_id, description):
    service_user = users.get_current_user()
    solution_server_settings = get_solution_server_settings()
    def trans():
        q = Question.get_by_id(question_id)
        if q:
            qr = QuestionReply(parent=q)
            qr.author = service_user
            qr.timestamp = now()
            qr.description = description
            qr.visible = False
            qr.put()
            sln_settings = get_solution_settings(users.get_current_user())
            message = """Please reply to %s (%s) with the following link:
%s/internal/shop/questions

Title:
%s

Description:
%s""" % (sln_settings.login.email() if sln_settings.login else "", users.get_current_user(), get_server_settings().baseUrl, q.title, description)
            send_mail(get_server_settings().senderEmail, solution_server_settings.solution_qanda_info_receivers,
                      q.title, message, transactional=True)

            return ReturnStatusTO.create(True, None)
        sln_settings = get_solution_settings(service_user)
        return ReturnStatusTO.create(False, translate(sln_settings.main_language, SOLUTION_COMMON, 'Could not find question'))

    xg_on = db.create_transaction_options(xg=True)
    return db.run_in_transaction_options(xg_on, trans)

@rest("/common/qanda/recent/load", "get", read_only_access=True)
@returns(QuestionsWithCursorReturnStatusTO)
@arguments(count=(int, long), cursor=unicode)
def load_recent(count=10, cursor=None):
    service_user = users.get_current_user()
    sln_settings = get_solution_settings(service_user)
    new_cursor, questions = Question.get_recent(count, cursor, sln_settings.main_language)
    return QuestionsWithCursorReturnStatusTO.create(True, None, [QuestionTO.fromModel(q, False, sln_settings) for q in questions], new_cursor)


@rest("/common/qanda/myquestions/load", "get", read_only_access=True)
@returns(QuestionsWithCursorReturnStatusTO)
@arguments(count=(int, long), cursor=unicode)
def load_my_questions(count=10, cursor=None):
    service_user = users.get_current_user()
    new_cursor, questions = Question.get_my_questions(service_user, count, cursor)
    sln_settings = get_solution_settings(service_user)
    return QuestionsWithCursorReturnStatusTO.create(True, None, [QuestionTO.fromModel(q, True, sln_settings) for q in questions], new_cursor)
