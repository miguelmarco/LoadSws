# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - Action to load page content from a sage worksheet upload

    @copyright: 2007-2008 MoinMoin:ReimarBauer,
                2008 MoinMoin:ThomasWaldmann
                2014 Miguel Marco
    @license: GNU GPL, see COPYING for details.
"""

import os

from MoinMoin import wikiutil, config
from MoinMoin.action import ActionBase, AttachFile
from MoinMoin.PageEditor import PageEditor
from MoinMoin.Page import Page
from MoinMoin.security.textcha import TextCha
import tarfile
import tempfile
import shutil
import codecs

import htmlentitydefs, sys

from HTMLParser import HTMLParser



class HTML2MoinMoin(HTMLParser):

    start_tags = {
        "a"     : " [%(0)s ",
        "b"     : "'''",
        "em"    : "''",
        "tt"    : "{{{",
        "pre"   : "\n{{{",
        "p"     : "\n\n",
        "br"    : "\n\n",
        "h1"    : "\n\n= ",
        "h2"    : "\n\n== ",
        "h3"    : "\n\n=== ",
        "h4"    : "\n\n==== ",
        "h5"    : "\n\n===== ",
        "title" : "TITLE: ",
        "table" : "\n",
        "tr"    : "",
        "td"    : "||"
        }

    end_tags = {
        "a"     : ']',
        "b"     : "'''",
        "em"    : "''",
        "tt"    : "}}}",
        "pre"   : "}}}\n",
        "p"     : "",
        "h1"    : " =\n\n",
        "h2"    : " ==\n\n",
        "h3"    : " ===\n\n",
        "h4"    : " ====\n\n",
        "h5"    : " =====\n\n",
        "table" : "\n",
        "tr"    : "||\n",
        "dt"    : ":: "
        }

    def __init__(self):
        HTMLParser.__init__(self)
        self.string = ''
        self.output = sys.stdout
        self.list_mode = []
        self.preformatted = False
        self.verbose = 0

    def clear(self):
        self.string = ''

    def parsed(self):
        return self.string

    def write(self, text):
        self.string += text


    def do_ul_start(self, attrs, tag):
        self.list_mode.append("*")

    def do_ol_start(self, attrs, tag):
        self.list_mode.append("1.")

    def do_dl_start(self, attrs, tag):
        self.list_mode.append("")

    def do_ul_end(self, tag):
        self.list_mode = self.list_mode[:-1]

    do_ol_end = do_ul_end
    do_dl_end = do_ul_end

    def do_li_start(self, args, tag):
        self.write("\n" + " " * len(self.list_mode) + self.list_mode[-1])

    def do_dt_start(self, args, tag):
        self.write("\n" + " " * len(self.list_mode) + self.list_mode[-1])

    def do_pre_start(self, args, tag):
        self.preformatted = True
        self.write(self.start_tags["pre"])

    def do_pre_end(self, tag):
        self.preformatted = False
        self.write(self.end_tags["pre"])

    def handle_starttag(self, tag, attrs):
        func = HTML2MoinMoin.__dict__.get("do_%s_start" % tag,
                                         HTML2MoinMoin.do_default_start)
        if ((func == HTML2MoinMoin.do_default_start) and
            self.start_tags.has_key(tag)):
            attr_dict = {}
            i = 0
            for a in attrs:
                attr_dict[a[0]] = a[1]
                attr_dict[str(i)] = a[1]
                i += 1
            self.write(self.start_tags[tag] % attr_dict)
        else:
            func(self, attrs, tag)

    def handle_endtag(self, tag):
        func = HTML2MoinMoin.__dict__.get("do_%s_end" % tag,
                                         HTML2MoinMoin.do_default_end)
        if ((func == HTML2MoinMoin.do_default_end) and
            self.end_tags.has_key(tag)):
            self.write(self.end_tags[tag])
        else:
            func(self, tag)

    def handle_data(self, data):
        if self.preformatted:
            self.write(data)
        else:
            self.write(data.replace("\n", " "))

    def handle_charref(self, name):
        self.write(name)

    def handle_entityref(self, name):
        if htmlentitydefs.entitydefs.has_key(name):
            self.write(htmlentitydefs.entitydefs[name])
        else:
            self.write("&" + name)

    def do_default_start(self, attrs, tag):
        if self.verbose:
            print "Encountered the beginning of a %s tag" % tag
            print "Attribs: %s" % attrs

    def do_default_end(self, tag):
        if self.verbose:
            print "Encountered the end of a %s tag" % tag


class SubirHoja(ActionBase):
    """ Load page action

    Note: the action name is the class name
    """
    def __init__(self, pagename, request):
        ActionBase.__init__(self, pagename, request)
        self.use_ticket = True
        _ = self._
        self.form_trigger = 'Load'
        self.form_trigger_label = _('Load')
        self.pagename = pagename
        self.method = 'POST'
        self.enctype = 'multipart/form-data'

    def do_action(self):
        """ Load """
        status = False
        _ = self._
        form = self.form
        request = self.request
        # Currently we only check TextCha for upload (this is what spammers ususally do),
        # but it could be extended to more/all attachment write access
        if not TextCha(request).check_answer_from_form():
            return status, _('TextCha: Wrong answer! Go back and try again...')

        comment = form.get('comment', u'')
        comment = wikiutil.clean_input(comment)

        file_upload = request.files.get('file')
        if not file_upload:
            # This might happen when trying to upload file names
            # with non-ascii characters on Safari.
            return False, _("No file content. Delete non ASCII characters from the file name and try again.")

        filename = file_upload.filename
        rename = form.get('rename', '').strip()
        if rename:
            target = rename
        else:
            target = filename

        target = wikiutil.clean_input(target)

        if target:
            tmpdir = tempfile.mkdtemp()
            swsfile = os.path.join(tmpdir,'worksheet.sws')
            fff = open(swsfile, 'wb')
            fff.write(file_upload.stream.read())
            fff.close()
            swstarfile = tarfile.open(swsfile)
            swstarfile.extractall(path=tmpdir)
            swstarfile.close()
            txtfile = open(os.path.join(tmpdir, 'sage_worksheet/worksheet.txt'))
            l = txtfile.readlines()
            txtfile.close()
            shutil.rmtree(tmpdir)
            l.pop(0)
            l.pop(0)
            bloques = []
            cadena = ''
            i = 0
            while l:
                lin = l.pop(0)
                if lin[:3] == '{{{':
                    bloques.append(cadena)
                    cadena = '{{{#!sagecell\n'
                    i += 1
                    lin = l.pop(0)
                    while lin[:3] != '///':
                        cadena += lin
                        lin = l.pop(0)
                        i += 1
                    cadena += '}}}\n'
                    bloques.append(cadena)
                    cadena = ''
                    while lin[:3] != '}}}':
                        lin = l.pop(0)
                        i+=1
                else:
                    cadena+=lin

            bloques2=[]
            p = HTML2MoinMoin()
            for l in bloques:
                if l[:13] == '{{{#!sagecell':
                    bloques2.append(p.parsed())
                    p.clear()
                    bloques2.append(l)
                else:
                    p.feed(l)
            filecontent = ''
            for l in bloques2:
                for i in l:
                    try:
                        filecontent += i.encode()
                    except:
                        pass
            self.pagename = target
            oldtext = Page(request, self.pagename).get_raw_body()
            pg = PageEditor(request, self.pagename)
            try:
                msg = pg.saveText(_(oldtext + filecontent), 0, comment=comment)
                status = True
            except pg.EditConflict, e:
                msg = e.message
            except pg.SaveError, msg:
                msg = unicode(msg)
        else:
            msg = _("Pagename not specified!")
        return status, msg

    def do_action_finish(self, success):
        if success:
            url = Page(self.request, self.pagename).url(self.request)
            self.request.http_redirect(url)
        else:
            self.render_msg(self.make_form(), "dialog")

    def get_form_html(self, buttons_html):
        _ = self._
        return """
<h2>%(headline)s</h2>
<p>%(explanation)s</p>
<dl>
<dt>%(upload_label_file)s</dt>
<dd><input type="file" name="file" size="50" value=""></dd>
<dt>%(upload_label_rename)s</dt>
<dd><input type="text" name="rename" size="50" value="%(pagename)s"></dd>
<dt>%(upload_label_comment)s</dt>
<dd><input type="text" name="comment" size="80" maxlength="200"></dd>
</dl>
%(textcha)s
<p>
<input type="hidden" name="action" value="%(action_name)s">
<input type="hidden" name="do" value="upload">
</p>
<td class="buttons">
%(buttons_html)s
</td>""" % {
    'headline': _("Upload page content"),
    'explanation': _("You can upload content for the page named below. "
                     "If you change the page name, you can also upload content for another page. "
                     "If the page name is empty, we derive the page name from the file name."),
    'upload_label_file': _('File to load page content from'),
    'upload_label_comment': _('Comment'),
    'upload_label_rename': _('Page name'),
    'pagename': wikiutil.escape(self.pagename, quote=1),
    'buttons_html': buttons_html,
    'action_name': self.form_trigger,
    'textcha': TextCha(self.request).render(),
}

def execute(pagename, request):
    """ Glue code for actions """
    SubirHoja(pagename, request).render()

