#!/usr/bin/env python3.9

from telethon import TelegramClient, events
from datetime import datetime
from dateutil.relativedelta import relativedelta  # pip install python-dateutil
from plexapi.server import PlexServer

import plexapi.exceptions
import asyncio
import aiosqlite
import re
import os
import urllib.request
import urllib.error
import sys
from decouple import config

session = config('session_name')
api_id = config('api_id', cast=int)
api_key = config('api_key')
bot_token = config('bot_token')
# Ogni quanti secondi interroga Plex
interroga = config('interroga', cast=int)
serverIp = config('serverIp')
serverToken = config('serverToken')
adminId = config('adminId', cast=int)


# ''''''''''''''''''''''''''''''''''''''''''''''''''''''
# colori
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# ..................................................................
# Abilita color in windows…
# ..................................................................
if os.name == 'nt':
    os.system('color')

# ..................................................................
# Verifica connessione..................... todo: :)
# ..................................................................
try:
    urllib.request.urlopen("http://google.com", timeout=10)
except urllib.error.URLError:
    print(f"[{bcolors.FAIL}Impossibile collegarsi a internet {bcolors.ENDC}]")
    sys.exit()

# ..................................................................
# Nuovo client telegram
# ..................................................................
client = TelegramClient(session, api_id, api_key, retry_delay=10)

# ..................................................................
# bot start
# ..................................................................
client.start(bot_token=bot_token)


class Database:
    def __init__(self, file_name: str):
        self.file_name = file_name
        self.db = None

    @staticmethod
    async def console(message: str):
        now = datetime.now()
        date_now = datetime.today().strftime('%d-%m-%Y')
        time_now = now.strftime("%H:%M:%S")
        print(f"<{date_now} {time_now}> {message}")

    async def connect(self):
        self.db = await aiosqlite.connect(self.file_name)
        return self.db

    # ..................................................................
    # Creo una tabella per gli utenti in prova 24h
    # ..................................................................
    async def create_table(self, table: str):
        try:
            page_table = f"""CREATE TABLE IF NOT EXISTS {table} (
                            id             INTEGER PRIMARY KEY AUTOINCREMENT
                                                   UNIQUE
                                                   NOT NULL,
                            nome        TEXT,
                            email       TEXT UNIQUE,
                            scadenza    TEXT,                        
                            stato       TEXT,
                            userid      TEXT UNIQUE,
                            invito      TEXT
                        );"""
            await self.db.execute(page_table)
        except Exception as e:
            await self.console(f"[Database create_table] Errore {e}. Segnala l'errore")

    async def select_all(self, table):
        try:
            cursor = await self.db.execute(f"SELECT * FROM {table} WHERE stato!='scaduto'")
            return await cursor.fetchall()
        except Exception as e:
            await self.console(f"[Database] select_all Errore {e}. Segnala l'errore")

    async def select_email(self, table, user_email):
        try:
            cursor = await self.db.execute(f"SELECT * FROM {table} WHERE email=?", (user_email,))
            result = await cursor.fetchall()
            if result:
                return result[0]
        except Exception as e:
            await self.console(f"[Database] select_email Errore {e}. Segnala l'errore")

    async def select_status(self, table, user_email):
        try:
            cursor = await self.db.execute(f"SELECT stato FROM {table} WHERE email=?", (user_email,))
            result = await cursor.fetchone()
            if result:
                return result[0]
        except Exception as e:
            await self.console(f"[Database] select_status Errore {e}. Segnala l'errore")

    async def delete_user(self, table: str, user_email: str):
        await self.db.execute(f"DELETE FROM {table} WHERE email=? AND invito!='accettato'", (user_email,))
        await self.db.commit()

    async def read_invite(self, table: str, user_email: str):
        cursor = await self.db.execute(f"SELECT invito FROM {table} WHERE email=?", (user_email,))
        return (await cursor.fetchone())[0]

    async def delete_useremail(self, table: str, user_email: str):
        await self.db.execute(f"DELETE FROM {table} WHERE email=?", (user_email,))
        await self.db.commit()

    async def update_status(self, table: str, user_email: str, stato: str):
        await self.db.execute(f"UPDATE {table} SET stato=? WHERE email=?", (stato, user_email,))
        await self.db.commit()

    async def update_scadenza(self, table: str, user_email: str, scadenza: str):
        await self.db.execute(f"UPDATE {table} SET scadenza=? WHERE email=?", (scadenza, user_email,))
        await self.db.commit()

    async def update_to_Nan(self, table: str, user_email: str):
        # result.rowcount = 1 Update query eseguita
        # La query deve essere eseguita solo una volta per passare dallo stato di plex24 a 'invalido'
        # e stampare il messaggio di email invalida solo una volta

        try:
            result = await self.db.execute(f"INSERT INTO {table} (nome,email, scadenza, stato, userid, invito) values"
                                           f" (?,?,?,?,?,?)", ('Nan', user_email, '1999-12-31 00:00', 'invalido',
                                                               'invalido', 'invalido'))
            await self.db.commit()
            if result.rowcount == 1:
                await self.console(f"[Plex Nan] L'email {user_email} non riconsciuta come un Plex account.")
        except aiosqlite.IntegrityError:
            # è già presente nel database
            pass

    async def update_invite(self, table: str, user_email: str, stato):
        await self.db.execute(f"UPDATE {table} SET invito=? WHERE email=?", (stato, user_email,))
        await self.db.commit()

    async def new_user(self, table, username, user_email, scadenza, stato, userid) -> bool:

        try:
            await self.db.execute(f"INSERT INTO {table} (nome,email, scadenza, stato, userid, invito) values (?,?,?,"
                                  f"?,?,?)",
                                  (username, user_email, scadenza, stato, userid, 'invitato'))
            await self.db.commit()
            await self.console(f"[Database] L'utente {username} {user_email} è stato aggiunto nel database.")
            return True
        except aiosqlite.IntegrityError:
            await self.console(f"[Database] L'utente {username} {user_email} risulta già registrato nel database")
            return False
        except Exception as e:
            await self.console(f"[Database] Errore :{e} segnala questo errore")
            return False

    async def close(self):
        await self.db.close()


class MyPlex:

    def __init__(self, server_ip: str, server_token: str):

        # Crea l'oggetto plex
        self.plex_token = server_token
        self.server_ip = server_ip
        self.baseurl = f'http://{self.server_ip}:32400'
        self.plex = PlexServer(self.baseurl, self.plex_token)
        self.db_users = Database("plex24.db")

        self._user_table = []
        self._invites_table = []

    @staticmethod
    async def console(message: str):
        now = datetime.now()
        date_now = datetime.today().strftime('%d-%m-%Y')
        time_now = now.strftime("%H:%M:%S")
        print(f"<{date_now} {time_now}> {message}")

    # ..................................................................
    # verifica base su stringa email
    # ..................................................................
    @staticmethod
    async def email_validate(email: str) -> bool:
        regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if re.fullmatch(regex, email):
            return True
        else:
            return False

    # .........................................................
    # Nuova connessione al database
    # .........................................................
    async def connect(self):
        await self.db_users.connect()

    # .........................................................
    # Nuova connessione al database
    # .........................................................
    async def close(self):
        await self.db_users.close()

    # .........................................................
    # Invita un amico nel server Plex
    # .........................................................
    async def invite_friend(self, nuova_email: str, librerie: list, username: str) -> bool:
        try:
            # lancia l'invito e assegna le librerie presenti nell'elenco sections
            self.plex.myPlexAccount().inviteFriend(user=nuova_email, server=self.plex, sections=librerie)
            # username non sempre presente(?)
            if not username:
                username = ''
            await self.console(f"[Plex invite] Nuovo invito per l'utente {username} {nuova_email} ")
            return True
        except plexapi.exceptions.BadRequest:
            await self.console(
                f"[Plex invite] l'utente {username} {nuova_email} risulta già essere nell'elenco friends.")
            return True
        except Exception as e:
            print(f"[Plex invite] {e} segnala questo errore")
            return False

    # .........................................................
    # Rimuovi un user dalla lista friend
    # .........................................................

    async def remove_friend(self, user_email: str):

        """
        Rimuovi un user dalla lista friend

        :param user_email: l'indirizzo email dell'utente da cercare
        :return: True se l'utente è stato rimosso, False altrimenti
        """
        try:
            self.plex.myPlexAccount().removeFriend(user_email)
            await self.db_users.delete_useremail('plex24h', user_email=user_email)
            await self.console(f"[Plex Kick] l'utente {user_email} è stato rimosso dalla friendlist")
            return True
        except (plexapi.exceptions.NotFound, plexapi.exceptions.BadRequest):
            await self.console(f"[Plex Kick] l'utente {user_email} non risulta essere in friendlist")
            return False

    async def search_friend(self, user_email) -> bool:

        """
        Cerca un amico associato all'admin in base all'indirizzo email dell'utente.

        :param user_email: l'indirizzo email dell'utente da cercare
        :return: True se l'utente è un amico dell'admin, False altrimenti
        """

        users = await self.list_users()
        return any(user_email in user for user in users)

    async def update_user(self, user_email: str, librerie: list):

        """
        Aggiorno lo stato di un friend

        :param user_email: l'indirizzo email dell'utente da cercare
        :param librerie: elenco delle librerie condivise
        :return: True se la condivisione è andata a buon fine, False altrimenti
        """

        if await self.search_friend(user_email=user_email) is False:
            await self.console(f"[Plex Update User] Non posso condividere le librerie se l'utente non"
                               f" nell'elenco friends")

        try:
            self.plex.myPlexAccount().updateFriend(user=user_email, server=self.plex, sections=librerie)
            return True
        except KeyError:
            await self.console(f'[Plex Update User] Errore: nessuna libreria disponibile')
            return False

    async def unshare_user(self, user_email: str) -> bool:

        """
        Rimuovo tutte le librerie condivise per l'utente

        :param user_email: l'indirizzo email dell'utente da cercare
        :librerie: elenco delle librerie condivise
        :return: True se ha rimosso tutte le librerie condivise, False altrimenti
        """

        # Se l'email non è valida non provo a fare nessun unshare
        invito = await self.db_users.read_invite('plex24h', user_email=user_email)
        if invito == 'invalido':
            return False

        # Legge i titoli di tutte librerie disponibili
        librerie = await self.list_sections()
        # Con removeSections = True occorre anche elencare le librerie condivise
        try:
            self.plex.myPlexAccount().updateFriend(user=user_email, server=self.plex, removeSections=True,
                                                   sections=librerie)
            return True
        except KeyError:
            await self.console(f'[Plex unshare] Una delle librerie non è disponibile {user_email}')
            return False
        except plexapi.exceptions.NotFound:
            await self.console(f"[Plex unshare] L'email {user_email} non è associato al tuo account Plex")
            return False

    async def list_invites(self) -> list:

        """
        Crea una lista con tutti gli inviti in pending

        return: una lista con tutti gli inviti in attesa di essere confermati , altrimeni ritorna una lista vuota
        """

        import math
        invites = self.plex.myPlexAccount().pendingInvites()
        for user in invites:
            # Se l'indirizzo email dell'invitato fosse non confermato come utente plex o inesistente,
            # non sarebbe possibile cancellare l'invito in questo caso l'oggetto user a il suo id assumono
            # il valore di 'nan'
            if not math.isnan(user.id):
                self._invites_table.append([user.email, user.username])
            else:
                await self.db_users.update_to_Nan('plex24h', user.email)
        return self._invites_table

    async def cancel_invite(self, user_email) -> bool:

        """
        Cancella un invito in pending

        :param user_email: l'indirizzo email dell'utente da cercare
        :return: True se ha cancellato l'invito dell'Admin, False altrimenti
        """

        try:
            self.plex.myPlexAccount().cancelInvite(user_email)
            await self.db_users.delete_user('plex24h', user_email=user_email)
            await self.console(f"[Plex delete invite] La richiesta di invito per l'utente <{user_email}>"
                               f" è stata annullata")
            return True
        except plexapi.exceptions.NotFound:
            await self.console(f"[Plex delete invite] Non è stata trovata nessuna richiesta attiva per l'utente "
                               f"<{user_email}>")
            return False

    async def list_sections(self) -> list:

        """
        Cancella un invito in pending

        :return: ritorna un elenco di librerie, elenco vuoto altrimenti
        """

        try:
            sections = self.plex.library.sections()
            sections_table = [section.title for section in sections]
            return sections_table
        except plexapi.exceptions.NotFound:
            return []

    async def list_users(self) -> list:

        """
        Cancella un invito in pending

        :return: ritorna un elenco di utenti friends dell'Admin, elenco vuoto altrimenti
        """
        self._user_table = [[user.username, user.email, user.id] for user in self.plex.myPlexAccount().users() if
                            user.email]
        return self._user_table


class PlexAdmin(MyPlex):
    def __init__(self, server_ip: str, server_token: str):
        # Per il momento dati hardcoded
        super().__init__(server_ip=server_ip, server_token=server_token)
        self.server_ip = server_ip
        self.server_token = server_token

    @staticmethod
    async def commands(user_cmd: str) -> bool:

        commands_list_param = ["/plex24 ", "/plexdel ", "/plexkick ", "/plexfull ", "/plexmese "]
        for cmd in commands_list_param:
            if user_cmd.lower().startswith(cmd):
                return True

        commands_list = ["/ping"]
        for cmd in commands_list:
            if user_cmd.lower() == cmd:
                return True

    async def cmd_email(self, cmd: str, stato: str) -> str:

        """
        In un comando con un solo parametro email verifica il numero di parametri e la stringa email
        :return: ritorna esito
        """

        # verifica che il numero di parametri sia corretto
        usercmd = cmd.lower().split()
        if len(usercmd) != 2:
            await self.console(
                f"Email non valida: devi inserire solo la tua email dopo il comando /{stato}. Esempio: /{stato} "
                "paolo.rossi@gmail.com")
            return ''
        user_email = usercmd[1]

        # verifica base solo su nome email
        if not await self.email_validate(email=user_email):
            await self.console(f"{user_email} Email invalida o incompleta")
            return ''
        return user_email

    async def prova24h(self, cmd: str, userid: str, username: str, stato: str) -> bool:

        """
        Crea una prova24

        :return: ritorna esito
        """

        nuova_email = await self.cmd_email(cmd=cmd, stato=stato)
        if not nuova_email:
            return False

        # Legge i titoli di tutte librerie disponibili
        librerie = await self.list_sections()

        # Calcola la scadenza
        scadenza = datetime.now() + relativedelta(days=+1)

        # Se non ci sono problemi con il database spedisce l'invito..
        result = await self.invite_friend(nuova_email, librerie, username)

        # Inserisce nel db il nuovo utente. Se è già presente da errore e ritorna
        if result is True:
            return await self.db_users.new_user('plex24h', username, nuova_email, scadenza.strftime("%Y-%m-%d %H:%M"),
                                                stato, userid)
        return False

    async def plexm(self, cmd: str, userid: str, username: str, stato: str) -> (bool, str):

        """
        Crea una prova da 1 mese

        :return: ritorna esito
        """

        # la sintassi è /plexmese mesi email ( esattamente 3 parametri)
        params = cmd.split(' ')
        if len(params) != 3:
            return False, ''

        # il mumero di mesi deve essere essere un numero intero senza lettere o punteggiatura
        if not params[1].isnumeric():
            return False, ''

        # il periodo massimo è tre mesi
        if int(params[1]) > 3:
            return False, ''

        # Verifica base dell'email
        if not await self.email_validate(email=params[2]):
            await self.console(f"{params[2]} Email invalida o incompleta")
            return False, ''

        # Email confermata
        nuova_email = params[2]

        # Legge i titoli di tutte librerie disponibili
        librerie = await self.list_sections()

        # Calcola la scadenza
        periodo = int(params[1])
        scadenza = datetime.now() + relativedelta(months=+periodo)

        # Se non ci sono problemi con il database spedisce l'invito..
        result = await self.invite_friend(nuova_email, librerie, username)

        # Inserisce nel db il nuovo utente. Se è già presente da errore e ritorna
        if result is True:
            return await self.db_users.new_user('plex24h', username, nuova_email, scadenza.strftime("%Y-%m-%d %H:%M"),
                                                stato, userid), f"{periodo} mese" if periodo == 1 else f"{periodo} mesi"
        return False, ''

    # ...................................................................
    #  account full access
    # ...................................................................
    async def full_access(self, cmd: str, userid: str, username: str, stato: str) -> bool:

        """
        Invita un account bypassando la prova24 oppure trasforma una prova24 in corso o scaduta in una registrazione
        senza scadenza

        :return: ritorna esito
        """

        user_email = await self.cmd_email(cmd=cmd, stato=stato)
        if not user_email:
            return False

        # Verifico se l'utente è già stato registrato o se si tratta di una nuova registrazione
        user_data = await self.db_users.select_email('plex24h', user_email)

        # Se l'utente è già stato registrato allora aggiorno il suo stato in 'fullaccess'
        # verificando prima che non sia già scaduto. In quel caso assegno anche le librerie.
        # Quando è scaduto infatti le librerie vengono rimosse dalla condivisione.
        if user_data:
            record, username, user_email, scadenza, stato, telegram_userid, invito = user_data
            if 'scaduto' in stato:
                await self.update_user(user_email=user_email, librerie=await self.list_sections())
            await self.db_users.update_status('plex24h', user_email, 'fullaccess')
            await self.db_users.update_scadenza('plex24h', user_email, '2099-01-01 00:00')
            return True
        else:
            # Altrimenti lo inserisco come nuovo utente
            librerie = await self.list_sections()

            # Se non ci sono problemi con il database spedisce l'invito..
            result = await self.invite_friend(user_email, librerie, username)

            # Inserisce nel db il nuovo utente. Se è già presente da errore e ritorna
            if result is True:
                return await self.db_users.new_user('plex24h', username, user_email, '2099-01-01 00:00', stato, userid)
        return False

    # ..........................................................
    # Crea un elenco di richieste plex24 precedentemente salvate
    # nel database
    # ..........................................................
    async def load_requests(self) -> list:
        """
        Crea un elenco di richieste plex24 precedentemente salvate nel database
        :return param: ritorna esito
        """

        # Crea un elenco di richieste plex24 precedentemente salvate nel database
        h24_register = await self.db_users.select_all('plex24h')

        # Legge l'elenco del db e controlla chi ha ancora una richiesta attiva
        db_invitati = [[user_data[2], user_data[6]] for user_data in h24_register if user_data[6] == 'invitato']
        return db_invitati

    # ..........................................................
    # Verifica inviti se accettati o declinati dall'utente
    # ..........................................................
    async def plex_requests(self):

        # Premesse:
        # dopo aver lanciato il comando /plex24 <email>
        # 1) Se l'user sceglie di rimuoversi dall'elenco friend oppure l'Admin lo kikka
        #    il record su db rimane e rimane nello stato di accettato. Non è più possibile fare un'altra prova.
        # 2) Se il record viene cancellato dal DB e l'utente fa parte dell'elenco friend
        #    il bot avverte in telegram che è tutto ok e aggiorna il db con una nuova richiesta
        #    l'invito viene visto dal bot come accettato perchè in realtà già friend.

        # Crea un elenco di friends associati all' Admin
        friends = await self.list_users()
        # Crea un elenco d'inviti attivi in questo momento
        plex_invites = await self.list_invites()

        # Crea un elenco di richieste plex24 precedentemente salvate nel database
        db_email_invitati = await self.load_requests()

        # Legge l'elenco friends e verifica se esiste un user con richiesta plex24 attiva nel db (stato = invitato)
        for friend_username, friend_user_email, friend_userid in friends:
            if any(friend_user_email in lista for lista in db_email_invitati):
                await self.console(
                    f"[Plex request] L'utente <{friend_user_email} {friend_username}> ha accettato l'invito")
                await self.db_users.update_invite('plex24h', friend_user_email, 'accettato')
                # await client.send_message(entity=-1001528086687, message=f"L'utente {friend_username}"
                #                                                         f" ha accettato l'invito")

        # Confronta le richieste di plex24 con gli inviti in plex ancora attivi
        for invite_user_email, invite_username in plex_invites:
            # Esiste un invito di Plex con un record associato nel db ?
            if any(invite_user_email in lista for lista in db_email_invitati):
                await self.console(f"[Plex request] In attesa di conferma dall'utente"
                                   f" <EMAIL:{invite_user_email} NAME:{invite_username}>")
            else:
                # Esiste un invito attivo in plex
                # Non esiste alcun record nel db per l'invito associato.
                # Controlliamo che non sia una richiesta fullaccess
                result = await self.db_users.select_status('plex24h', invite_user_email)
                if result and result != 'fullaccess':
                    # Non esiste alcun record con stato uguale a fullaccess
                    await self.console(f"[Plex request] L'utente"
                                       f" <EMAIL:{invite_user_email} NAME:{invite_username}>"
                                       f" ha declinato l'invito !")

        if not plex_invites:
            # Aggiorno elenco di richieste plex24 da db. Se esistono richieste attive (invitato) e non ci sono inviti
            # su plex attivi le richieste vengono considerate declinate e vengono cancellate dal db.
            db_invitati = await self.load_requests()

            for db_invitato_email, invito in db_invitati:
                if invito == 'invitato':
                    await self.console(f"[Plex request2] L'utente"
                                       f" <EMAIL:{db_invitato_email}>"
                                       f" ha declinato l'invito !")
                    await self.db_users.delete_user('plex24h', db_invitato_email)

    # ...................................................................
    #  Verifica scadenza prova 24h e prova 1 mese
    # ...................................................................
    async def plex_scadenze(self):
        # Controlla gli utenti Plex24h e Plex1m

        users = await self.db_users.select_all('plex24h')
        for record, username, user_email, scadenza, stato, userid, invito in users:
            try:
                scadenza = datetime.strptime(scadenza, "%Y-%m-%d %H:%M")
            except ValueError as e:
                await self.console(f"[BOT] [UserName:{username}][Email:{user_email}]  [Scadenza:{scadenza}]"
                                   f" Segnala l'errore {e}")
                return

            if datetime.now() > scadenza and stato != 'scaduto':
                # Invio una notifica all'Admin
                await client.send_message(entity=adminId, message=f"Nome: {username} Email: {user_email} "
                                                                  f"Periodo scaduto !")

                # Scaduto il tempo rimuove le librerie ma non rimuove l'utente dall'elenco amici dell'Admin
                await self.db_users.update_status('plex24h', user_email, 'scaduto')
                result = await self.unshare_user(user_email=user_email)

                # Avvisa con un messaggio in "console"
                if result:
                    await self.console(f"[UserId:{userid}] [UserName:{username}][Email:{user_email}] Periodo Scaduto !")

    async def plex_kick(self, cmd: str) -> bool:

        """
        Rimuovi un user dalla lista friend

        :return: ritorna esito
        """

        user_email = await self.cmd_email(cmd=cmd, stato='kick')
        if not user_email:
            return False
        return await self.remove_friend(user_email=user_email)

    async def plexdel(self, cmd) -> bool:

        """
        Rimuovi un invito

        :return: ritorna esito
        """

        user_email = await self.cmd_email(cmd=cmd, stato='del')
        if not user_email:
            return False

        return await self.cancel_invite(user_email)

    # ...................................................................
    #  Controlla lo stato del server plex e del bot
    # ...................................................................
    async def stat99(self) -> str:
        status = f""" 
        FriendlyName: {self.plex.friendlyName}
        Platform: {self.plex.platform} {self.plex.platformVersion}
        Plex Version: {self.plex.version}
        """
        return status


# ...................................................................
#  Eventi da telegram
# ...................................................................

@client.on(events.NewMessage())
async def handler(message):
    cmd = message.text.lower()
    sender = await message.get_sender()

    if message.is_private:
        if not sender.bot:
            plex_Admin = PlexAdmin(server_ip=serverIp, server_token=serverToken)
            if not await plex_Admin.commands(cmd):
                await plex_Admin.console(
                    f"[BOT] {bcolors.WARNING}- {sender.username} il tuo comando '{cmd}' non è valido -"
                    f"{bcolors.ENDC}")
                await client.send_message(entity=message.chat_id,
                                          message=f"il tuo comando '{cmd}' non è valido.")
                await plex_Admin.console(f"{bcolors.OKGREEN}- ok -{bcolors.ENDC}")
                return
            await plex_Admin.connect()

            # ...................................................................
            #  /plex24
            # ...................................................................
            if cmd.startswith('/plex24 '):
                await plex_Admin.console(
                    f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")

                result = await plex_Admin.prova24h(cmd=cmd, userid=str(sender.id), username=sender.username,
                                                   stato='plex24')
                if result is False:
                    await plex_Admin.console(f"[BOT] [UserId:{sender.id}] '{sender.username}' Richiesta respinta'")
                    # Il bot risponde all'utente
                    await client.send_message(entity=message.chat_id,
                                              message="Questa email non è valida oppure è già stata registrata.")
                else:
                    await client.send_message(entity=message.chat_id,
                                              message="OK. Se non hai un account Plex controlla la tua email. "
                                                      "Altrimenti fai il Login in Plex e accetta il mio invito. Grazie")

            # ...................................................................
            # Admin commands
            #
            if sender.id == adminId:
                # ...................................................................
                #  /plexkick
                # ...................................................................

                if cmd.startswith('/plexkick '):
                    await plex_Admin.console(
                        f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")
                    result = await plex_Admin.plex_kick(cmd=cmd)
                    if result:
                        await client.send_message(entity=message.chat_id,
                                                  message="Utente rimosso.")
                    else:
                        await client.send_message(entity=message.chat_id,
                                                  message="L'utente non risulta essere in friendlist.")

                # ...................................................................
                #  /plexdel invitation
                # ...................................................................

                if cmd.startswith('/plexdel '):
                    await plex_Admin.console(
                        f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")
                    result = await plex_Admin.plexdel(cmd=cmd)
                    if result:
                        await client.send_message(entity=message.chat_id,
                                                  message="Invito cancellato.")
                    else:
                        await client.send_message(entity=message.chat_id,
                                                  message="Non esiste un invito per questo utente.")

                # ...................................................................
                #  /ping il bot legge alcune informazioni dal server plex
                # ...................................................................

                if cmd.startswith('/ping'):
                    await plex_Admin.console(
                        f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")
                    result = await plex_Admin.stat99()
                    if result:
                        await client.send_message(entity=message.chat_id, message=result)
                    await plex_Admin.console(f"[PLEX Stat]' {result}")

                # ...................................................................
                #  /plexfull crea un account senza scadenza o converte il plex24
                # ...................................................................

                if cmd.startswith('/plexfull '):
                    await plex_Admin.console(
                        f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")
                    result = await plex_Admin.full_access(cmd=cmd, userid=str(sender.id), username=sender.username,
                                                          stato='plexfull')
                    if result is False:
                        await plex_Admin.console(f"[BOT] [UserId:{sender.id}] '{sender.username}' Richiesta respinta'")
                        # Il bot risponde all'utente
                        await client.send_message(entity=message.chat_id,
                                                  message="Questa email non è valida oppure è già stata registrata.")
                    else:
                        await client.send_message(entity=message.chat_id,
                                                  message="OK. Utente in 'fullaccess'.")

                # ...................................................................
                #  /plexmese crea un account con 1 mese di scadenza
                # ...................................................................

                if cmd.startswith('/plexmese '):
                    await plex_Admin.console(
                        f"[BOT] [UserId:{sender.id}] '{sender.username}' ha inviato il comando '{cmd}'")

                    result, periodo = await plex_Admin.plexm(cmd=cmd, userid=str(sender.id), username=sender.username,
                                                             stato='plexmese')

                    if result is False:
                        await plex_Admin.console(f"[BOT] [UserId:{sender.id}] '{sender.username}' Richiesta respinta'")
                        # Il bot risponde all'utente
                        await client.send_message(entity=message.chat_id,
                                                  message="Questa email non è valida oppure è già stata registrata.")
                    else:
                        await client.send_message(entity=message.chat_id,
                                                  message="Ok grazie per la tua donazione sei stato abilitato"
                                                          f" per {periodo} a partire da ora, accetta l' invito"
                                                          " e riavvia l' app Plex.")

                await plex_Admin.close()
                await plex_Admin.console(f"{bcolors.OKGREEN}- ok -{bcolors.ENDC}")


# ....................................................
# TIMER ogni quanto interroga Plex
# .....................................................
async def wait_until(dt):
    await asyncio.sleep(dt)


async def run_at(dt, coro):
    dt = max(10, min(dt, 7200))
    await wait_until(dt)
    return await coro


async def live():
    """
    today = date.today()
    now = datetime.now()
    timenow = now.strftime("%H:%M:%S")
    print(f"<{today} {timenow}>{bcolors.OKGREEN} - ok -{bcolors.ENDC}\r")
    """


async def main():
    # Inizializza Plex Admin
    plex_Admin = PlexAdmin(server_ip=serverIp, server_token=serverToken)

    # Connessione al server
    await plex_Admin.connect()

    # Controllo scadenze prova 24h
    await plex_Admin.plex_scadenze()

    # Controllo inviti in pending
    await plex_Admin.plex_requests()

    # Chiudo fino al prossimo check
    await plex_Admin.close()


#######################################################
# START !
#######################################################
async def start():
    db_users = Database("plex24.db")
    result = await db_users.connect()
    if not result:
        loop.stop()
        return

    await db_users.create_table('plex24h')
    await db_users.close()
    print(f"[{bcolors.OKGREEN}ctrl-c per uscire{bcolors.ENDC}]")
    await live()
    while True:
        await main()
        await run_at(interroga, live())


loop = asyncio.get_event_loop()
try:
    print()
    print(f"[{bcolors.OKGREEN}START !{bcolors.ENDC}]")
    task_start = loop.create_task(start())
    loop.run_forever()

except KeyboardInterrupt:
    pass
finally:
    pass
