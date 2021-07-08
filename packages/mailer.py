import smtplib
import imaplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# from email.header import Header
from jinja2 import Environment, FileSystemLoader
import os
import pandas as pd
import re
from tinydb import TinyDB, Query
import logging

ma_logger = logging.getLogger('mediatheker.ma')


class Mailer:
    def __init__(self, config, subscribers, available_movies):
        self.config = config
        #template directory for jinja
        self.env = Environment(
            loader=FileSystemLoader(self.config['TEMPLATE']['path']))

        # strat config
        self.imap_ssl_host = self.config['MAIL']['imap_host']
        self.imap_ssl_port = int(self.config['MAIL']['imap_port'])
        self.smtp_ssl_host = self.config['MAIL']['smtp_host']
        self.smtp_ssl_port = int(self.config['MAIL']['smtp_port'])
        # use username or email to log in
        self.username = self.config['MAIL']['email']
        self.password = self.config['MAIL']['password']

        #db config
        self.subscribers = subscribers
        self.available_movies = available_movies
        self.Subs = Query()

    def send_mail(self, to_email, subject, bodyContent):
        from_email = self.config['MAIL']['email']
        message = MIMEMultipart()
        message['Subject'] = subject# Header(subject,'utf-8',errors='ignore')
        message['From'] = '{user} <{mail}>'.format(user=self.config['MAIL']['email_name'], mail=self.config['MAIL']['email'])
        message['To'] = to_email
        
        message.attach(MIMEText(bodyContent, "html"))#,'utf-8'))
        msgBody = message.as_string()

        # we'll connect using SSL
        server = smtplib.SMTP_SSL(self.smtp_ssl_host, self.smtp_ssl_port)
        # to interact with the server, first we log in
        # and then we send the message
        server.login(self.username, self.password)
        server.sendmail(from_email, to_email, msgBody)
        server.quit()

    #flag can be regular, all, or summary
    # regular = regular daily newsletter
    # summary = all movies with given rating
    # all = all movies available
    def prepare_newsletter(self,subscriber, movies, flag='regular'):
        if flag == 'regular' or flag == 'summary':
            movies = movies.query('rating >= {rating}'.format(rating=subscriber['rating']))

        # if flag != 'all' and (not subscriber['first'] or flag == 'summary'):
        if flag == 'regular' and not subscriber['first']:
            movies = movies.query('type == "new"')
        
        movies = movies.sort_values(by = 'rating', ascending=False)

        if len(movies) > 0:
            info = {'username' : subscriber['firstname'], 'moviecount' : len(movies), 'rating' : subscriber['rating'], 'flag' : flag, 'service_email' : self.config['MAIL']['email']}
            newsletter = self.newsletter_factory(info,movies)
            if flag == 'regular':
                subject = '🍿 Es gibt neue Filme!'
            elif flag == 'summary':
                subject = '🍿 Hier sind deine Filme'
            else:
                subject = '🍿 Hier sind alle Filme'

            return {'to_address': subscriber['email'], 'subject' : subject, 'body': newsletter}
        return False

    def prepare_reply(self, subscriber, flag):
        info = {'username' : subscriber['firstname'], 'rating': subscriber['rating'],'flag': flag, 'service_email' : self.config['MAIL']['email']}
        if flag == 'stop':
            subject = 'Newsletter abbestellt!'
        elif flag == 'rating':
            subject = 'Rating angepasst!'
        elif flag == 'subscribe':
            subject = 'Abonniert!'
        elif flag == 'unknown':
            subject = 'Das habe ich nicht verstanden...'
        elif flag == 'download':
            subject = 'Download-Info'
        elif flag == 'rerun' or flag == 'rerun-false':
            subject = 'Rerun erhalten'
        elif flag == 'feedback':
            subject = 'Danke für dein Feedback!'
        else:
            return False
        template = self.env.get_template(self.config['TEMPLATE']['reply'])
        body = template.render(info=info)
        return {'to_address': subscriber['email'], 'subject' : subject, 'body': body}



    def newsletter_factory(self,info, movies):
        template = self.env.get_template(self.config['TEMPLATE']['movies'])
        return template.render(movies=movies, info=info)

    def imap_login(self):
        # connect to the server and go to its inbox
        mail = imaplib.IMAP4_SSL(self.imap_ssl_host,self.imap_ssl_port)
        mail.login(self.username, self.password)
        return mail

    def get_mails(self):
        mail = self.imap_login()
        # we choose the inbox but you can select others
        status, messages = mail.select('inbox')
        # total number of emails
        messages = int(messages[0])
        mails = []
        
        # we choose the inbox but you can select others
        mail.select('inbox')

        status, data = mail.search(None, 'ALL')
        mail_ids = []
        for block in data:
            mail_ids += block.split()

        for i in mail_ids:
            status, data = mail.fetch(i, '(RFC822)')

            curr_mail = {}
            for response_part in data:
                if isinstance(response_part, tuple):
                    message = email.message_from_bytes(response_part[1])
                    

                    From, encoding = decode_header(message['from'])[0]
                    if isinstance(From, bytes):
                        From = From.decode(encoding)
                        mail_from  = [From, re.findall(r'<(.*)>', str(decode_header(message['from'])[1][0]))[0]]
                    else:
                        try:
                            mail_from = [re.findall(r'^(.*)<', message['from'])[0], re.findall(r'<(.*)>',message['from'])[0]]
                        except:
                            mail_from = [message['from'],message['from']]

                    # mail_subject = message['subject']

                    subject, encoding = decode_header(message['subject'])[0]
                    if isinstance(subject, bytes):
                        # if it's a bytes, decode to str
                        mail_subject = subject.decode(encoding)
                    else:
                        mail_subject = message['subject']

                    if message.is_multipart():
                        mail_content = ''

                        for part in message.get_payload():
                            if part.get_content_type() == 'text/plain':
                                mail_content += part.get_payload(decode=True).decode('utf-8','ignore')
                    else:
                        mail_content = message.get_payload(decode=True).decode('utf-8','ignore')

                    curr_mail['from'] = mail_from
                    curr_mail['subject'] = mail_subject
                    curr_mail['body'] = mail_content
            mails.append(curr_mail)
        mail.close()
        mail.logout()
        return mails

    def delete_all_mails(self):
        mail = self.imap_login()
        mail.select('Inbox')
        typ, data = mail.search(None, 'ALL')
        for num in data[0].split():
            mail.store(num, '+FLAGS', '\\Deleted')
        mail.expunge()
        mail.close()
        mail.logout()

    def send_newsletter(self,specific_user = None):
        movies = pd.DataFrame.from_dict(self.available_movies.all())
        send_counter = 0
        update_counter = 0

        if specific_user:
            sub_iterator = self.subscribers.search(self.Subs.email == specific_user['email'])
        else:
            sub_iterator = self.subscribers
        
        if not sub_iterator:
            return False

        for subscriber in sub_iterator:
            newsletter = self.prepare_newsletter(subscriber, movies)
            if newsletter:
                self.send_mail(newsletter['to_address'],newsletter['subject'],newsletter['body'])
                if subscriber['first']:
                    self.subscribers.update({'first' : False}, self.Subs.email == subscriber['email'])
                    update_counter += 1
                ma_logger.info('newsletter sent to {user}.'.format(user=newsletter['to_address']))
                send_counter += 1
        return [send_counter, update_counter]