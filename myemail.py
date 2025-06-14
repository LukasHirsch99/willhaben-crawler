import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class Email:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = self.cfg.get("name")
        self.server = self.cfg.get("server")
        self.port = int(self.cfg.get("port"))
        self.user = self.cfg.get("user")
        self.pw = self.cfg.get("pw")
        self.sender = self.cfg.get("from")
        self.to = self.cfg.get("to")
        self.subject = self.cfg.get("subject")

    def Send(self, content: str | list[str]):
        smtpServer = smtplib.SMTP(host=self.server, port=self.port)
        smtpServer.starttls()
        smtpServer.login(self.user, self.pw)

        msg = MIMEMultipart()

        msg["From"] = self.sender
        msg["To"] = self.to
        msg["Subject"] = self.subject

        if isinstance(content, list):
            sl = []
            sl.append("<html><body>")
            for e in content:
                sl.append(str(e))
            sl.append("</body></html>")
            mailText = "".join(sl)
        else:
            mailText = "<html><body>{}</body></html>".format(content)
        msg.attach(MIMEText(mailText, "html", "utf-8"))
        smtpServer.send_message(msg)

        del msg
        smtpServer.quit()
        del smtpServer
