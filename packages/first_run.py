from tinydb import TinyDB, Query
import yaml
import os
import platform
from crontab import CronTab
from shutil import copyfile

class FirstRun:
    def __init__(self):
        self.example_config_file = 'res/config_example.yaml'
        self.config_file = 'config.yaml'

    def start_db(self):
        config_yaml = open(self.config_file,'r')
        config = yaml.load(config_yaml, Loader=yaml.FullLoader)
        config_yaml.close()

        print("Hey there, it seems like you are new here. Let's start by creating the database with your admin information.")
        admin_name = input('First things first: how can I call you?\n')
        admin_mail = input("And what's your email?\n")
        admin_rating = input("Which iMDb rating should I store for you (0.0-10.0)?\n")
        
        db = TinyDB(config['DB']['path'])
        subscribers = db.table(config['DB']['subscribers'])
        admin = {'firstname' : admin_name, 'email': admin_mail, 'admin' : True, 'first' : True, 'rating' : admin_rating}
        subscribers.insert(admin)
        db.close()
        print("Alright, I created the database for you with you as the admin of the service.")

    def start_config(self):
        config_yaml = open(self.example_config_file,'r')
        config = yaml.load(config_yaml, Loader=yaml.FullLoader)
        config_yaml.close()

        print("We need to setup the service's email account.")
        email_name = input("What should be the name of your mailing service your subscribers see in their inbox (e.g. Movie Mail)?\n")
        email = input("And what's the email address you would like to send the newsletter from (has to be different from the admin mail)?\n") 
        password = input('And the password please:\n')
        imap_host = input("What's the IMAP address of your mail service?\n")
        imap_port = input('Can you tell me the port of the IMAP server?\n')
        smtp_host = input('Next I need the SMTP server address:\n')
        smtp_port = input('And its port:\n')

        config['MAIL']['imap_host'] = imap_host
        config['MAIL']['imap_port'] = int(imap_port)
        config['MAIL']['smtp_host'] = smtp_host
        config['MAIL']['smtp_port'] = int(smtp_port)
        config['MAIL']['email_name'] = email_name
        config['MAIL']['email'] = email
        config['MAIL']['password'] = password

        copyfile(self.example_config_file,self.config_file)

        config_yaml = open(self.config_file,'w')
        config_yaml.write(yaml.dump(config))
        config_yaml.close()

        print("Perfect, I created the config file for you.")
    
    def start_cronjob(self):
        if platform.system() == 'Linux':
            crontab = input("Seems like you are running this app on Linux. Would you like to setup a cronjob for the mediatheker and the mail_service?\n")
            if crontab == "yes":
                system_user = input("For which user (user name) would you like to install the cronjob?\n")
                cwd = os.getcwd()
                try:
                    cron = CronTab(user=system_user)
                    mediatheker = False
                    mail_service = False
                    for job in cron:
                        if "mediatheker" in job.command:
                            mediatheker = True
                        if "mail_service" in job.command:
                            mail_service = True
                    
                    if mediatheker:
                        print("mediatheker cronjob already exists. Skipping...")
                    else:
                        print("At what time should the mediatheker run every day?")
                        hour = input("Hour:\n")
                        minute = input("Minute:\n")

                        job = cron.new(command=f"python3 {cwd}/mediatheker.py -l")
                        job.hour.on(hour)
                        job.minute.on(minute)
                        cron.write()
                        print("I created the following cronjob for mediatheker.py:")
                        print(job.command)

                    if mail_service:
                        print("mail_service cronjob already exists. Skipping...")
                    else:
                        print("How often would you like to run the mail_service for your subscribers?")
                        minute = input("Every XX Minutes:\n")

                        job = cron.new(command=f"python3 {cwd}/mail_service.py")
                        job.minute.every(minute)
                        cron.write()
                        print("I created the following cronjob for mail_service.py:")
                        print(job.command)
                    print('Cronjobs created successfully')
                except:
                    print(f"Error while creating the cronjob for '{system_user}'. Please restart the process.")
            else:
                print('Skipping cronjob creation.')


