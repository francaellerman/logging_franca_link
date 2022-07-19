import logging
import json
import flask
import datetime
import warnings
import sqlite3

#Simplified from https://stackoverflow.com/a/70223539/11141301
class DictFormatter(logging.Formatter):
    """
    Formatter that outputs Python dictionaries after parsing the LogRecord.
    """
    def formatMessage(self, record) -> dict:
        return record.__dict__

    def formatTime(self, record):
        return datetime.datetime.utcnow().isoformat() + 'Z'

    def format(self, record) -> str:
        if record.levelname == 'WARNING':
            warnings.warn('There was a logging warning')
        #record.message = record.getMessage()
        #Should be allowed to not specify format, see https://docs.python.org/3/library/logging.html#logging.Formatter.formatTime
        record.asctime = self.formatTime(record)
        message_dict = self.formatMessage(record)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.stack_info:
            message_dict["stack_info"] = self.formatStack(record.stack_info)
        return message_dict

class JsonFormatter(DictFormatter):
    def format(self, record):
        r = json.dumps(super().format(record), default=str)
        print(type(r))
        return r

class EmailFormatter(DictFormatter):
    keys = ['name', 'msg', 'levelname', 'flask_path', 'flask_method','ID', 'asctime']
    def format(self, record):
        d = super().format(record)
        try:
            d['ID'] = EmailFormatter.returning_user_name(d['ID'])
        except:
            pass
        body = [f'{key}:\n              {d[key]}' for key in EmailFormatter.keys]
        return '\n'.join(body)
    def returning_user_name(id_):
        con = sqlite3.connect('connections/connections.sql')
        return list(con.cursor().execute(
            "select name from students where id = ?",
            [int(id_)]))[0][0]

class connections_filter(logging.Filter):
    def filter(self, record):
        #Only allows warnings+ unless it's a non-ignorable user because I
        #want to see who's going to my site :)
        return ((record.name.startswith('franca_link') and not record.__dict__.get('ignore')) or record.levelno >= 30) and record.msg.find('Using fallback font') == -1

class email_filter(connections_filter):
    def filter(self, record):
        return super().filter(record) and not record.__dict__.get('flask_path') == '/calculator/api'

def set_up_logging():
    global EmailHandler
    global JsonFormatter
    global EmailFormatter
    global connections_filter
    global email_filter
    logging.captureWarnings(True)
    #No parameters to getLogger returns root logger
    root = logging.getLogger()
    root.setLevel(level=logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler('franca_link.log', maxBytes=10**6, backupCount=5)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)
    handler.addFilter(connections_filter())
    root.addHandler(handler)
    with open('/etc/franca_link/email_address.txt') as f:
        from_ = f.readline().rstrip()
        to = f.readline().rstrip()
    class EmailHandler(logging.handlers.SMTPHandler):
        def getSubject(self, record):
            return record.msg
    email_handler = EmailHandler(mailhost='127.0.0.1',
            fromaddr = from_, toaddrs=[to], subject='Connections log')
    email_handler.setFormatter(EmailFormatter())
    email_handler.addFilter(email_filter())
    root.addHandler(email_handler)

class wrapper_related:
    def __init__(self, name):
        self.logger = logging.getLogger(name)

    def extra(self, id_=None):
        ip = flask.request.environ.get('HTTP_X_REAL_IP',
                flask.request.remote_addr)
        student_id = id_ if id_ else flask.session.get('ID')
        return {'IP': ip, 'ID': student_id,
                'ignore': flask.request.cookies.get('ignore'),
                'flask_path': flask.request.path,
                'flask_method': flask.request.method}

    def info(self, message, id_=None):
        self.logger.info(message, extra=self.extra(id_))

    def exception(self, id_=None):
        self.logger.exception("Runtime exception", extra=self.extra(id_))

    def wrapper(self, message=None):
        def inner(func):
            def inner_inner():
                nonlocal message
                try:
                    resp = func()
                    if not message:
                        message = 'Request success'
                    self.info(message)
                    return resp
                except:
                    self.exception()
                    return flask.abort(500)
            inner_inner.__name__ = func.__name__
            return inner_inner
        return inner
