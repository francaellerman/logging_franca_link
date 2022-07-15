import logging
import json
import flask
import datetime

#Simplified from https://stackoverflow.com/a/70223539/11141301
class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def formatMessage(self, record) -> dict:
        return record.__dict__

    def formatTime(self, record):
        return datetime.datetime.utcnow().isoformat() + 'Z'

    def format(self, record) -> str:
        if record.levelname == 'WARNING':
            warnings.warn('There was a logging warning')
        record.message = record.getMessage()
        #Should be allowed to not specify format, see https://docs.python.org/3/library/logging.html#logging.Formatter.formatTime
        record.asctime = self.formatTime(record)
        message_dict = self.formatMessage(record)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message_dict["exc_info"] = record.exc_text
        if record.stack_info:
            message_dict["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(message_dict, default=str)

def set_up_logging():
    global JsonFormatter
    logging.captureWarnings(True)
    #No parameters to getLogger returns root logger
    root = logging.getLogger()
    root.setLevel(level=logging.DEBUG)
    class connections_filter(logging.Filter):
        def filter(self, record):
            #Only allows warnings+ unless it's a non-ignorable user because I
            #want to see who's going to my site :)
            return ((record.name.startswith('franca_link') and not record.__dict__.get('ignore')) or record.levelno >= 30) and record.msg.find('Using fallback font') == -1
    handler = logging.handlers.RotatingFileHandler('franca_link.log', maxBytes=10**6, backupCount=5)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)
    handler.addFilter(connections_filter())
    root.addHandler(handler)
    with open('/etc/franca_link/email_address.txt') as f:
        from_ = f.readline().rstrip()
        to = f.readline().rstrip()
    email_handler = logging.handlers.SMTPHandler(mailhost='localhost',
            fromaddr = from_, toaddrs=[to], subject='Connections log')
    email_handler.addFilter(connections_filter())
    #root.addHandler(email_handler)

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
