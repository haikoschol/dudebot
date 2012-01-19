#!/usr/bin/env python
# -*- coding: utf-8 -*-

from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from twisted.python import log
import os, time, sys, re, signal, cPickle, urllib, httplib, random
import google

class Users(dict):
    def lastSeen(self, nick):
        if not self.has_key(nick):
            return nick + " wurde noch nie gesehen."
        timestamp = self[nick]
        return nick + " wurde zuletzt am " + time.strftime("%d.%m.%y", timestamp) + " um " \
               + time.strftime("%H:%M:%S", timestamp) + " gesehen."

    def addOrUpdate(self, nick):
        self[nick] = time.localtime(time.time())

class Plugin:
    ''' superclass of all plugins. a plugin must have an atribute "command", stating on
        what command the plugin should be invoked, and a method called handleCommand().
        the return value of this method will be ignored. the first argument of this
        method is a reference to the bot that invoked the method. this argument can be
        used to communicate with the irc channel the bot is on.
        a plugin can have a method handlePrivmsg() that gets called on any privmsg. '''

    ''' this string must be in uppercase! '''
    command = 'GENERIC_PLUGIN_COMMAND'

    ''' contains a description how to use the plugin (syntax, etc.), does not get a
        reference to the bot, because printing the help to a channel is handled by
        the help plugin '''
    help = 'superclass of all plugins'

    ''' "argument" is what is given to the bot after the "command" string, may be empty '''
    def handleCommand(self, bot, nick, channel, argument=None):
        pass

class HelpPlugin(Plugin):
    command = 'HELP'
    help = 'Syntax: "help <command>" oder "help all" fuer eine liste aller Befehle.'

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None:
            bot.msg(channel, self.help)
            return
        argument = argument.strip()
        if argument == '': bot.msg(channel, self.help)
        else:
            if argument == 'all':
                result = ''
                for i in bot.plugin_list:
                    result += i.lower() + ', '
                result = result[:-2]
                bot.msg(channel, result)
            else:
                tmp = bot.getPluginForCommand(argument)
                if tmp is None:
                    bot.msg(channel, 'Es wurde kein Plugin fuer den Befehl ' \
                            + argument + ' geladen.')
                else:
                    bot.msg(channel, tmp.help)

class SeenPlugin(Plugin):
    command = 'SEEN'
    help = 'Liefert einen Zeitstempel wann ein Nick das letzte mal benutzt wurde. \
        Syntax: seen <nick>'

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: return
        argument = argument.strip()
        bot.msg(channel, bot.user_list.lastSeen(argument))

    def handlePrivmsg(self, bot, nick, channel, msg):
        bot.user_list.addOrUpdate(nick)

class MemoPlugin(Plugin):
    command = 'MEMO'
    help = 'Speichert ein Memo an einen Nick. Das naechste Mal wenn der Benutzer des Nick '
    help += 'etwas sagt wird das Memo zugestellt. Memos die mir per Query mitgeteilt werden '
    help += 'behandle ich natuerlich vertraulich und teile sie dem Empfaenger auch per Query mit. '
    help += 'Syntax: memo <nick> <text>'

    def __init__(self):
        self.memos = {}
        self.memo_regex = re.compile('\s*(\S+)\s+(.*)')

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: return
        m = self.memo_regex.match(argument)
        if not m:
            bot.msg(channel, 'Syntax Fehler')
        else:
            tmp = m.groups()
            new_memo = {}
            if channel == nick:
                new_memo['channel'] = tmp[0]
            else:
                new_memo['channel'] = channel
            new_memo['memo'] = tmp[0] + ', Memo von ' + nick + ' (' + time.strftime('%d.%m.%y')\
                               + ', ' + time.strftime('%H:%M:%S') + '): ' + tmp[1]
            if not self.memos.has_key(tmp[0]):
                self.memos[tmp[0]] = []
            self.memos[tmp[0]].append(new_memo)
            bot.msg(channel, 'Memo gespeichert.')

    def handlePrivmsg(self, bot, nick, channel, msg):
        if not self.memos.has_key(nick): return
        tmp = self.memos[nick]
        for i in tmp:
            bot.msg(i['channel'], i['memo'])
        del self.memos[nick]

class InfoPlugin(Plugin):
    command = 'INFO'
    help = 'Plugin zum Abrufen und Eintragen von Zuordnungen zwischen Woertern und einem \
        Text. Syntax: "info <Wort> = <Text>" zum Eintragen und "info <Wort>" zum Abrufen.'
    def __init__(self):
        self.infos = {}
        self.info_regex = re.compile('\s*(\S+)(?:\s+=\s+(.*))?')

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: return
        m = self.info_regex.match(argument)
        if m is None:
            bot.msg(channel, 'Syntax Fehler.')
            return
        tmp = m.groups()
        if tmp[1] is not None:
            self.infos[tmp[0]] = tmp[1]
            bot.msg(channel, 'Info gespeichert.')
        else:
            if self.infos.has_key(tmp[0]):
                bot.msg(channel, self.infos[tmp[0]])
            else:
                bot.msg(channel, 'Sorry, dazu hab ich nix gespeichert.')

class CalculatorPlugin(Plugin):
    ''' actually just calls eval(), but dont tell anyone! '''
    command = 'CALC'
    help = 'Evaluiert mathematische Ausdruecke. Um Operatoren herum muessen Leerzeichen stehen (z.B. 1 + 2, nicht 1+2). Syntax: calc <Ausdruck>'

    def __init__(self):
        self.sanitize_regex = re.compile('[{}\[\]]|system|exec')
        self.allowed_regex = re.compile('\(?0x[\d,a-f,A-F]+\)?|\(?\d+\)?|\+|-|\*|/|\(|\)|pow\(.*?\)|hex\(.*?\)|sqrt\(.*?\)')
        
    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: return
        m = self.sanitize_regex.search(argument)
        if m is not None:
            result = 'fnord'
#        result = ''
#        split_arg = argument.split()
#        m_list = [self.allowed_regex.match(a) for a in split_arg]
#        i = 0
#        for m in m_list:
#            if m != split_arg[i]:
#                result = 'fnord'
#                break
#            i += 1
#        if result != 'fnord':
        else:
            try:
                result = eval(argument)
            except:
                result = 'fnord'
        if result is not '': bot.msg(channel, result)

class ClockPlugin(Plugin):
    command = 'ZEIT'
    help = 'Gibt die aktuelle Uhrzeit aus. Syntax: zeit'

    def __init__(self):
        self.time_regex = re.compile('Die Uhrzeit: <font color="#000000">(\S+)</font> am (\S+)<br>')

    def handleCommand(self, bot, nick, channel, argument=None):
        try:
            sock = urllib.urlopen('http://www.uhrzeit.org/')
        except: return
        data = sock.read()
        sock.close()
        m = self.time_regex.search(data)
        if m is not None:
            tmp = m.groups()
            result = 'Es ist jetzt genau ' + tmp[0] + ' Uhr. Heute ist der ' + tmp[1] \
                      + '. (http://www.uhrzeit.org/)'
        else:
            result = 'Es ist jetzt ungefaehr ' + time.strftime('%H:%M:%S') \
                     + ' Uhr. Heute ist der ' + time.strftime('%d.%m.%y') + '.'
        bot.msg(channel, result)

class DictLeoOrgPlugin(Plugin):
    command = 'LEO'
    help = 'Uebersetzt von Deutsch nach Englisch und vice versa mittels http://dict.leo.org/.'
    help += ' Syntax: leo <Wort>'

    def __init__(self):
        self.baseurl = 'http://dict.leo.org/?relink=off&lang=en&search='
        self.words_regex = re.compile('<td class=\"td1\" valign=\"middle\" width=\"43%\">(.*?)</td>')
        self.crap_regex = re.compile('<.*?>|\xa0')
        self.max_results = 5

    def cleanUp(self, w):
        return self.crap_regex.sub('', w)

    def handleCommand(self, bot, nick, channel, argument=None):
        url = self.baseurl + argument.strip()
        try:
            sock = urllib.urlopen(url)
        except: return
        data = sock.read()
        sock.close()
        m = self.words_regex.findall(data)
        cleaned_up = [self.cleanUp(w) for w in m]
        if channel == nick: 
            length = len(cleaned_up)
        else:
            length = min(self.max_results * 2, len(cleaned_up))
        result = ''
        i = 0
        while i < length:
            if i+1 < len(cleaned_up):
                result += cleaned_up[i] + ' = ' + cleaned_up[i+1] + ' \ '
                i += 2

        bot.msg(channel, result[:len(result)-3])

class WikipediaPlugin(Plugin):
    command = 'WIKIPEDIA'
    help  = 'Liefert Links zu Wikipedia Artikeln. Durchsucht erst die deutsche '
    help += 'Wikipedia und bei Misserfolg die englische. Syntax: wikipedia <begriff>'

    def __init__(self):
        self.article_link_regex = re.compile('a href="/wiki/(?!Wikipedia|Portal|Hauptseite|Diskussion|Spezial|Bild|Kategorie)(\\S+)"')

    def constructURL(self, query, lang='en'):
        return (lang + '.wikipedia.org', '/wiki/' + query.replace(' ', '_'))

    def fetchPage(self, query, lang='en'):
        host, path = self.constructURL(query, lang)
        try:
            http = httplib.HTTP(host)
            http.putrequest('GET', path)
            http.putheader('User-Agent', 'Mozilla (compatible, harmless python script actually)')
            http.putheader('Host', host)
            http.putheader('Accept', '*/*')
            http.endheaders()
            errcode, errmsg, headers = http.getreply()
            if errcode > 399: return '', ''
            if errcode == 301 or errcode == 302:
                newurl = headers.getheader('Location')
                if newurl is not None:
                    queryindex = newurl.rfind('/')
                    try:
                        newquery = newurl[queryindex+1:]
                        newhost = newurl[newurl.find('//')+2:newurl.find('/wiki')]
                    except:
                        return '', ''
                    newhttp = httplib.HTTP(newhost)
                    newhttp.putrequest('GET', '/wiki/' + newquery)
                    newhttp.putheader('User-Agent', 'Mozilla (compatible, harmless python script actually)')
                    newhttp.putheader('Host', newhost)
                    newhttp.putheader('Accept', '*/*')
                    newhttp.endheaders()
                    newerrcode, newerrmsg, newheaders = newhttp.getreply()
                    f = newhttp.getfile()
                    page = f.read()
                    f.close()
                    return (newurl, page)

            url  = 'http://' + host + path
            f    = http.getfile()
            page = f.read()
            f.close()
        except:
#           the_bot.msg(channel, 'Exception in httplib')
            return '', ''
        return (url, page)

    def articleExists(self, page, lang='en'):
        if page == '': return False
        if lang == 'en':
            notFoundMsg = "Wikipedia does not have an article with this exact name"
        elif lang == 'de':
            notFoundMsg = "Diese Seite existiert nicht"
        else:
            return False
        return (page.find(notFoundMsg) < 0) and (page.strip() != '')

    def isAmbiguous(self, page, lang='en'):
        if page == '': return False
        if lang == 'de':
            ambig = 'Vorlage_Begriffsklaerung'
        else:
            return False
        return (page.find(ambig) > 0)

    def extractArticleLinks(self, page, lang='en', maxCount=0):
        result = ''
        count = 0
        for i in self.article_link_regex.findall(page):
            host, path = self.constructURL(i, lang)
            result += 'http://' + host + path + ' , '
            count += 1
            if maxCount > 0:
                if count == maxCount: return result[:-3]
        if result == '': return result
        return result[:-2]

    def handleCommand(self, bot, nick, channel, argument=None):
        lang = 'de'
        argument = argument.strip()
        url, page = self.fetchPage(argument, lang)
        if self.articleExists(page, lang):
            if self.isAmbiguous(page, lang):
                bot.msg(channel, 'Suchbegriff nicht eindeutig (' + url + '), die ersten n Artikel: ' + self.extractArticleLinks(page, 'de', 5))
            else:
                bot.msg(channel, url)
        else:
            url_en, page_en = self.fetchPage(argument)
            if self.articleExists(page_en):
                bot.msg(channel, url_en)
            else:
                bot.msg(channel, 'Leider nichts gefunden.')

class PortPlugin(Plugin):
    command = 'PORT'
    help  = 'Liefert zu einer Portnummer den Dienst der laut IANA fuer diesen Port registriert ist. '
    help += 'Syntax: port <Nummer> oder port <Nummer>/tcp oder port <Nummer>/udp oder port <Servicename> '
    help += '(momentan nur TCP Services).'
    
    def __init__(self):
        self.ports = {}
        self.ports['tcp'] = {}
        self.ports['udp'] = {}
        try:
            f = urllib.urlopen('http://www.iana.org/assignments/port-numbers')
        except: return
        page = f.read()
        f.close()
        tcp_regex   = re.compile('(\\S+)\\s+([0-9]+)/tcp\\s*(.*)')
        udp_regex   = re.compile('(\\S+)\\s+([0-9]+)/udp\\s*(.*)')
        pagelist    = page.split('\r\n')
        tcp_matches = [tcp_regex.search(i) for i in pagelist]
        udp_matches = [udp_regex.search(i) for i in pagelist]
        for i in tcp_matches:
            if i is not None:
                m = i.groups()
                self.ports['tcp'][m[1]] = m[0] + ' (' + m[2] + ')'
        for i in udp_matches:
            if i is not None:
                m = i.groups()
                self.ports['udp'][m[1]] = m[0] + ' (' + m[2] + ')'
                
    def getServiceByPort(self, port, proto='tcp'):
        if self.ports.has_key(proto):
            tmp = self.ports[proto]
            if tmp.has_key(port):
                return tmp[port]
        return None

    def getPortsByService(self, argument=None):
        if argument is None: return None
        result = []
        for i in self.ports['tcp']:
            if self.ports['tcp'][i].find(argument) > -1: result.append(i)
        return result
        
    def handleCommand(self, bot, nick, channel, argument=None):
        result = None
        if argument is None:
            bot.msg(channel, 'Syntax Fehler.')
            return
        argument = argument.strip()
        if argument.find('/tcp') > -1:
            result = self.getServiceByPort(argument[:-4], 'tcp')
        elif argument.find('/udp') > -1:
            result = self.getServiceByPort(argument[:-4], 'udp')
        else:
            try:
                int(argument)
                tmp = ''
                result = self.getServiceByPort(argument, 'tcp')
                if result is not None: tmp += 'tcp:  ' + result + '     '
                result = self.getServiceByPort(argument, 'udp')
                if result is not None: tmp += 'udp:  ' + result
                if result != '': result = tmp
            except:
                tmp = ''
                result = self.getPortsByService(argument)
                if result is not None and (len(result) > 0):
                    for i in result:
                        tmp += i + '/tcp | '
                    result = tmp[:-7]
        if result is not None: bot.msg(channel, result)
        else: bot.msg(channel, 'Nix gefunden.')
                
class GoogleFightPlugin(Plugin):
    command = 'GOOGLEFIGHT'
    help    = 'Ermittelt den Gewinner eines Google Fight zwischen 2 Woertern. '
    help   += 'Syntax: googlefight <wort1> <wort2>'
    
    class WordParseError:
        value = 'Syntax Error.'
        def __str__(self):
            return self.value
    
    def __init__(self):
        self.result_count_regex = re.compile('hr <b>(\\S+)</b> f')
        
    def parseWord(self, argument_list, index=0):
        if argument_list[index][0] == '"':
            if len(argument_list) < index+2: raise self.WordParseError
            word = ''
            found_quote = False
            while index < len(argument_list):
                word += argument_list[index] + ' '
                if argument_list[index][-1:] == '"': 
                    found_quote = True
                    break
                index += 1
            if not found_quote: raise self.WordParseError
            return word[:-1], index+1
        else:
            return argument_list[index], (index+1)
                
    def parseWords(self, argument):
        argument_list = argument.split()
        if len(argument_list) < 2:
            raise self.WordParseError
        try:
            word1, index = self.parseWord(argument_list)
        except self.WordParseError, arg:
            raise arg
        try:
            word2, index = self.parseWord(argument_list, index)
        except self.WordParseError, arg:
            raise arg
        return word1, word2

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: 
            bot.msg(channel, 'Syntax Fehler.')
            return
        try:
            word1, word2 = self.parseWords(argument)
        except self.WordParseError, arg:
            bot.msg(channel, arg)
            return
        try:
            word1_data = google.doGoogleSearch(word1)
            word2_data = google.doGoogleSearch(word2)
        except:
            bot.msg(channel, 'Exception in google.doGoogleSearch()')
            return
        
        if word1_data.meta.estimatedTotalResultsCount > word2_data.meta.estimatedTotalResultsCount:
            bot.msg(channel, word1 + ' hat gewonnen.')
        elif word2_data.meta.estimatedTotalResultsCount > word1_data.meta.estimatedTotalResultsCount:
            bot.msg(channel, word2 + ' hat gewonnen.')
        else:
            bot.msg(channel, 'Unentschieden.')


class RFCPlugin(Plugin):
    command = 'RFC'
    help = 'Sucht Links zu RFC Dokumenten via Google raus. '
    help += 'Syntax: rfc <protokollakronym>'
    
    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None:
            return
        try:
            data = google.doGoogleSearch('rfc: ' + argument)
        except:
            bot.msg(channel, 'Exception in google.doGoogleSearch()')
        if data is not None:
            bot.msg(channel, data.results[0].URL)


class GooglePlugin(Plugin):
    command = 'GOOGLE'
    resultcount = 5
    help = 'Liefert die ersten ' + str(resultcount) + ' Suchergebnisse'

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None:
            return
        if argument.find(' ') != -1:
            argument = '"' + argument + '"'
        try:
            data = google.doGoogleSearch(argument)
        except:
            bot.msg(channel, 'Exception in google.doGoogleSearch()')
            return
        links = ''
        if data is not None:
            for i in range(5):
                if len(data.results) >= i:
                    links += data.results[i].URL + ' | '
            bot.msg(channel, links[:-3])


class GoogleSpellPlugin(Plugin):
    command = 'GOOGLESPELL'
    help = 'Liefert "Buchstabiervorschlaege" via Google'

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None:
            return
        try:
            data = google.doSpellingSuggestion(argument)
        except:
            bot.msg(channel, 'Exception in google.doSpellingSuggestion()')
            return
        if data is not None: bot.msg(channel, data)
        else: bot.msg(channel, 'Leider nix am Start.')

class ChuckismPlugin(Plugin):
    command = 'CHUCKISM'
    help = 'Gibt ein zufaellig ausgewaehltes Faktum ueber Chuck Norris aus. (http://www.chucknorrisfacts.com/)'
    help += ' Syntax: chuckism'
    
    def __init__(self):
        self.chuckisms = []
        self.chuckism_regex = re.compile('<li>(.*?)</li>')
        try:
            f = urllib.urlopen('http://www.chucknorrisfacts.com/')
            for i in self.chuckism_regex.findall(f.read()):
                self.chuckisms.append(i.replace('&rsquo;', '\''))
            f.close()
            f = urllib.urlopen('http://www.chucknorrisfacts.com/additionalfacts.html')
            for i in self.chuckism_regex.findall(f.read()):
                self.chuckisms.append(i.replace('&rsquo;', '\''))
            f.close()
            f = urllib.urlopen('http://www.chucknorrisfacts.com/morefacts.html')
            for i in self.chuckism_regex.findall(f.read()):
                self.chuckisms.append(i.replace('&rsquo;', '\''))
            f.close()
        except: pass
        
    def getRandomChuckism(self):
        random.seed()
        if len(self.chuckisms) == 0:
            return 'Liste is leer :('
        return self.chuckisms[random.randint(0, len(self.chuckisms)-1)]
        
    def handleCommand(self, bot, nick, channel, argument=None):
        bot.msg(channel, self.getRandomChuckism())

class DecisionMakerPlugin(Plugin):
    command = 'WUERFEL'
    help = 'Waehlt zufaellig zwischen 2 oder mehr Moeglichkeiten. Syntax: wuerfel <moeglichkeit1>, <moeglichkeit2>, ...'    
    def __init__(self):
        pass
        
    def handleCommand(self, bot, nick, channel, argument=None):
        random.seed()
        decisions = argument.split(',')
        if (len(decisions) < 2) or (argument is None):
            bot.msg(channel, 'Syntax Fehler')
            return
        bot.msg(channel, random.choice(decisions))

class YubnubPlugin(Plugin):
    command = 'YUBNUB'
    help = 'Interface zu http://www.yubnub.org/. Syntax: yubnub <kommando>'

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None: return
        query = { 'command' : argument}
        try:
            u = urllib.urlopen('http://www.yubnub.org/parser/parse?' + urllib.urlencode(query))
        except: return
        if getattr(u, 'url') is not None:
            bot.msg(channel, u.url)

class BruceSchneierFactsPlugin(Plugin):
    command = 'SCHNEIERISM'
    help = 'Gibt ein zufaelliges Faktum ueber Bruce Schneier aus. (http://geekz.co.uk/schneierfacts/). Syntax: schneierism'

    def __init__(self):
        self.fact_regex = re.compile('<p class="fact">(.*?)</p>')

    def handleCommand(self, bot, nick, channel, argument=None):
        u = urllib.urlopen('http://geekz.co.uk/schneierfacts/')
        data = u.read()
        u.close()
        m = self.fact_regex.findall(data)
        if len(m) > 0:
            bot.msg(channel, m[0])

class AcronymExpansionPlugin(Plugin):
    command = 'DEFINE'
    help    = 'Definiert eine Abkuerzung mit Hilfe einer Google "define:" Suche. '
    help   += 'Syntax: define <acronym>'
    
    def __init__(self):
        self.definition_regex = re.compile('<ul type="disc">.*?<li>(.+)')
        
    def constructURL(self, query):
        query = "define:" + query
        encoded_query = urllib.urlencode({'q' : query})
        return 'www.google.de', '/search?' + encoded_query + '&start=0&ie=utf-8&oe=utf-8'
        
    def fetchPage(self, query):
		host, path = self.constructURL(query)
		try:
			http = httplib.HTTP(host)
			http.putrequest('GET', path)
			http.putheader('User-Agent', 'Mozilla (compatible, harmless python script actually)')
			http.putheader('Host', host)
			http.putheader('Accept', '*/*')
			http.endheaders()
			errcode, errmsg, headers = http.getreply()
			if errcode > 399: return None
			f    = http.getfile()
			page = f.read()
			f.close()
		except:
			return None
		return page
        
    def getDefinition(self, page):
        definition = self.definition_regex.search(page)
        if definition is not None and definition.groups()[0] != '':
            return definition.groups()[0]
        else:
            return None
            
    def define(self, acronym):
        msg = self.getDefinition(self.fetchPage(acronym))
        if msg is None:
            return 'Nix gefunden'
        else:
            return msg

    def handleCommand(self, bot, nick, channel, argument=None):
        if argument is None:
            bot.msg(channel, 'Syntax Fehler.')
            return
        bot.msg(channel, self.define(argument))

class DudeBot(irc.IRCClient):
    nickname = 'dimitri'

    def __init__(self):
        global the_bot
        the_bot = self
        google.setLicense('eDOOWdhQFHJhZ+4WTjIzq19UDl9vSNa+')
        self.logfile = open('dudebot.log', 'a')
        self.plugin_list = {}
        self.plugins_that_hook_privmsg = []
        self.has_joined = False
        self.user_list = Users()
        tmp = '^' + self.nickname + '[,|:|;]?\s+(\S+)(?:\s+(.*))?'
        self.command_regex = re.compile(tmp)
        self.query_command_regex = re.compile('^\s*(\S+)(?:\s+(.*))?')
        self.loadPlugins()

    def loadPlugins(self):
#        '''FIXME: plugins_that_hook_privmsg is ugly and not flexible '''
        try:
            fd = open('dudebot.pickle', 'r')
            self.plugins = cPickle.load(fd)
            fd.close()
        except:
            self.plugins = [HelpPlugin(), SeenPlugin(), MemoPlugin(), InfoPlugin(), \
                            CalculatorPlugin(), ClockPlugin(), DictLeoOrgPlugin(), \
                            WikipediaPlugin(), PortPlugin(), GoogleFightPlugin(), \
                            RFCPlugin(), GooglePlugin(), GoogleSpellPlugin(), \
                            DecisionMakerPlugin(), YubnubPlugin(), BruceSchneierFactsPlugin(),\
                            AcronymExpansionPlugin()]
        for i in self.plugins:
            self.plugin_list[i.command] = i
            if getattr(i, 'handlePrivmsg', None) is not None:
                self.plugins_that_hook_privmsg.append(i)

    def log(self, message):
        self.logfile.write(message + '\n')
        self.logfile.flush()

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)

    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
#        self.logfile.close()
        
    def signedOn(self):
        self.join(self.factory.channel)

    def joined(self, channel):
        self.has_joined = True

    def userJoined(self, user, channel):
        self.user_list.addOrUpdate(user)

    def userLeft(self, user, channel):
        self.user_list.addOrUpdate(user)

    def privmsg(self, user, channel, msg):
        if not self.has_joined: return
        tmp = user.split('!')
        nick = tmp[0]
        hostmask = (len(tmp) > 1) and tmp[1] or ''
        for i in self.plugins_that_hook_privmsg:
            i.handlePrivmsg(self, nick, channel, msg)
        self.dispatchCommand(nick, hostmask, channel, msg)

    def action(self, user, channel, msg):
        self.user_list.addOrUpdate(user)

    def kickedFrom(self, channel, kicker, message):
        self.join(channel)

    def irc_NICK(self, prefix, params):
        old_nick = prefix.split('!')[0]
        new_nick = params[0]
        self.user_list.addOrUpdate(old_nick)
        self.user_list.addOrUpdate(new_nick)

    def dispatchCommand(self, nick, hostmask, channel, msg):
        ''' checks if any command was given and a plugin is registered for it '''
        if self.nickname == channel:
            m = self.query_command_regex.match(msg)
            chan = nick
        else:
            m = self.command_regex.match(msg)
            chan = channel
        if m:
            cmd = m.groups()
            plugin = self.getPluginForCommand(cmd[0].upper())
            if plugin is not None:
                if len(cmd) == 2:
                    plugin.handleCommand(self, nick, chan, cmd[1])
                else:
                    plugin.handleCommand(self, nick, chan)

    def getPluginForCommand(self, command):
        ''' returns a reference to a plugin for a given command string '''
        command = command.upper()
        if self.plugin_list.has_key(command):
            return self.plugin_list[command]
        else:
            return None

class DudeBotFactory(protocol.ClientFactory):
    protocol = DudeBot

    def __init__(self, channel):
        self.channel = channel

    def clientConnectionLost(self, connector, reason):
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print 'connection failed:', reason
        reactor.stop()

def kill_handler(signal, frame):
#    print 'kill handler invoked, pickling plugins...'
    fd = open('dudebot.pickle', 'w')
    cPickle.dump(the_bot.plugins, fd)
    fd.close()
    os._exit(0)

if __name__=='__main__':
#    Log.startLogging(sys.stdout)
    global channel                 # ***FIXME***
    if len(sys.argv) > 1:
        channel = sys.argv[1]
    else:
        channel = 'ng-social'
    while True:
        try:
            f = DudeBotFactory(channel)
            #signal.signal(signal.SIGTERM, kill_handler)
            #signal.signal(signal.SIGINT, kill_handler)
            #signal.signal(signal.SIGHUP, kill_handler)
            reactor.connectTCP('irc.netgarage.org', 6667, f)
            reactor.run()
        except:
            time.sleep(10) 
