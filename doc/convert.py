import markdown
from markdown.preprocessors import Preprocessor
from markdown.postprocessors import Postprocessor
from markdown.blockprocessors import BlockProcessor
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension

import xml.etree.ElementTree as etree
import re
from os import listdir
from os.path import isfile, join


mdToHtmlName = {
    'CheatSheet' : 'cheat-sheet',
    'FunctionalProgramming' : 'deduce-programming',
    'ProofIntro' : 'deduce-proofs',
    'Reference' : 'reference',
    'SyntaxGrammar' : 'syntax',
    'GettingStarted' : 'getting-started'
}

mdToTitle = {
    'CheatSheet' : 'Cheat Sheet',
    'FunctionalProgramming' : 'Programming',
    'ProofIntro' : 'Proofs',
    'Reference' : 'Reference Manual',
    'SyntaxGrammar' : 'Syntax Overview',
    'GettingStarted' : 'Getting Started',
}

mdToDeduceCode = {
    'FunctionalProgramming' : 'programming',
    'ProofIntro' : 'proof',
    'Reference' : 'reference',
}


def safeHTMLify(s):
    return s.replace("<", "&lt;")\
            .replace(">", "&gt;")\
            .replace("\t", "    ")\
            .replace("\n", "<br>\n")\
            .replace(" ", "&nbsp;")\
            .replace("λ", "&#x03BB;")\
            .replace("≠", "&#x2260;")\
            .replace("≤", "&#x2264;")\
            .replace("≥", "&#x2265;")\
            .replace("⊆", "&#x2286;")\
            .replace("∈", "&#x2208;")\
            .replace("∪", "&#x222A;")\
            .replace("∩", "&#x2229;")\
            .replace("⨄", "&#x2A04;")\
            .replace("∘", "&#x2218;")\
            .replace("∅", "&#x2205;");

def unsafeHTMLify(s):
    return s.replace("&lt;", "<")\
            .replace("&gt;", ">")\
            .replace("&ast;", "*")\
            .replace("&amp;", "&")\
            .replace("&nbsp;", " ")\
            .replace("&#x03BB;", "λ")\
            .replace("&#x2260;", "≠")\
            .replace("&#x2264;", "≤")\
            .replace("&#x2265;", "≥")\
            .replace("&#x2286;", "⊆")\
            .replace("&#x2208;", "∈")\
            .replace("&#x222A;", "∪")\
            .replace("&#x2229;", "∩")\
            .replace("&#x2A04;", "⨄")\
            .replace("&#x2218;", "∘")\
            .replace("&#x2205;", "∅")\
            .replace("<br>\n", "\n")

class CodeBlockPreprocessor(Preprocessor):
    def run(self, lines):
        # otherwise it gets interpreted as a code block instead of our special code block
        # then make inequality signs safe for html then add back comments
        return [line.replace("```", "!!!")\
                    .replace("<", "&lt;")\
                    .replace(">", "&gt;")\
                    .replace("&lt;!--", "<!--")\
                    .replace("--&gt;", "-->") 
                for line in lines]

class CodeInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element('code', {'class': 'inline'})
        el.text = m.group(1)
        return el, m.start(0), m.end(0)

class BetterAnchorPostprocessor(Postprocessor):

    def replace_anchors(self, m):
        file = m.group(1)
        link = file
        is_local_md = (file.startswith('./') and file.endswith('.md')) or len(file) == 0
        if is_local_md and len(file) > 0:
            file = file[2:-3]
            link = './' + mdToHtmlName[file] + '.html'
        return f'<a href="{link}#{'' if m.group(3) is None else m.group(3)}" target="{'_self' if is_local_md else '_blank'}">'

    def run(self, text):
        PATTERN = r'<a +href="([^"#]*)(#([^"]*))?">'
        return re.sub(PATTERN, self.replace_anchors, text)

class CodeBlockProcessor(BlockProcessor):
    RE_FENCE_START = r'^ *!!!({\.deduce\^?#?(.*)})? *\n' # start line, e.g., `   !!!! `
    RE_FENCE_END = r'\n *!!!\s*$'  # last non-blank line, e.g, '!!!\n  \n\n'

    def __init__(self, parser, fname):
        self.fname = fname

    def test(self, parent, block):
        return re.match(self.RE_FENCE_START, block)

    def run(self, parent, blocks):
        original_block = blocks[0]

        m = re.search(r'^ *!!!{\.deduce\^#(.*)} *\n', blocks[0])
        blocks[0] = re.sub(self.RE_FENCE_START, '', blocks[0])

        for block_num, block in enumerate(blocks):
            if re.search(self.RE_FENCE_END, block):
                # remove fence
                blocks[block_num] = re.sub(self.RE_FENCE_END, '', block)
                # render fenced area inside a new div
                wrapper = etree.SubElement(parent, 'div', {'class' : 'code-wrapper' if m else 'code-wrapper non-deduce'})
                code = etree.SubElement(wrapper, 'code', {'id' : f'{mdToDeduceCode[self.fname]}_{m.group(1)}'} if m else {})

                code_text = []

                for i in range(0, block_num + 1):
                    code_text.append(blocks[0])
                    code_text.append("\n\n")
                    blocks.pop(0)

                code_text = code_text[:-1]
                code.text = '<!-- Generated by codeUtils.js -->' if m else safeHTMLify('\n'.join(code_text))
                if m: 
                    with open(f"./gh-pages/deduce-code/{mdToDeduceCode[self.fname]}_{m.group(1)}.pf", "w") as f:
                        # import everything for testing purposes
                        f.write("import Nat\nimport List\nimport Set\nimport MultiSet\nimport Maps\n\n")
                        f.write(unsafeHTMLify(''.join(code_text)))

                return True  # or could have had no return statement
        # No closing marker!  Restore and do nothing
        blocks[0] = original_block
        return False  # equivalent to our test() routine returning False

class CodeBlockTreeProcessor(Treeprocessor):
    def run(self, root):
        self.fix_codeblocks(root)

    def fix_codeblocks(self, element):
        for child in element:
            # Any code blocks that weren't caught by block processor
            if child.tag == 'pre':
                child.tag = 'div'
                child.set("class", "code-wrapper non-deduce")
                code = child.find('code')
                code.text = safeHTMLify(code.text)
            # asterisks in code blocks
            if child.tag == 'div' \
                    and 'code-wrapper' in child.get('class', default='') \
                    and child.find('code') is not None:
                # otherwise it gets interpreted as an italics tag
                child.find('code').text = child.find('code').text.replace("*", "&ast;")
            else: self.fix_codeblocks(child)

class CodeExtension(Extension):
    def __init__(self, fname):
        self.fname = fname

    def extendMarkdown(self, md):
        md.preprocessors.register(CodeBlockPreprocessor(), 'code-block-pre', 10000)
        md.inlinePatterns.register(CodeInlineProcessor(r'(?<!`)`([^`]*?)`(?!`)', md), 'code', 10000)
        md.parser.blockprocessors.register(CodeBlockProcessor(md.parser, self.fname), 'code-block', 10000)
        md.treeprocessors.register(CodeBlockTreeProcessor(), 'code-block-tree', 10000)
        md.postprocessors.register(BetterAnchorPostprocessor(), 'anchor', 10000)

prelude = lambda fname : f'''
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Deduce | {mdToTitle[fname]}</title>

    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="../images/logo.svg">

    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&family=Josefin+Slab:ital,wght@0,100..700;1,100..700&display=swap"
        rel="stylesheet">

    <!-- Font awesome -->
    <script src="https://kit.fontawesome.com/7005573326.js" crossorigin="anonymous"></script>

    <!-- My stylesheets -->
    <link rel="stylesheet" href="../css/normalize.css">
    <link rel="stylesheet" href="../css/style.css">
</head>

<body>

    <div class="container md {mdToHtmlName[fname]}">
        <nav>
            <a class="nav-logo" href="../index.html">
                <svg xmlns="http://www.w3.org/2000/svg" width="1668" height="402" fill="none" viewBox="0 0 1668 402">
                    <ellipse class="blue" cx="52.954" cy="86.34" fill="#5DAAF1" rx="42.5" ry="46"
                        transform="rotate(14.995 52.954 86.34)" />
                    <path class="blue" fill="#5DAAF1" d="m64.373 41.777 35.74 9.573-23.804 88.867-35.74-9.573z" />
                    <rect class="blue" width="89" height="109" x="79.397" y="28.202" fill="#5DAAF1" rx="26"
                        transform="rotate(14.995 79.397 28.202)" />
                    <rect class="blue" width="88" height="109" x="104.511" y="34.929" fill="#5DAAF1" rx="41"
                        transform="rotate(14.995 104.511 34.929)" />
                    <circle cx="102.759" cy="57.343" r="7.5" fill="#fff" transform="rotate(14.995 102.759 57.343)" />
                    <path class="blue" fill="#5DAAF1"
                        d="M138.713 51.92c-.708-2.633-.535-9.472 5.812-15.768 7.934-7.87 13.773-2.974 9.545 5.889-3.382 7.09-7.816 15.009-9.61 18.082l-5.747-8.203Z" />
                    <rect class="blue" width="277" height="144.529" x="159.042" y="50.663" fill="#5DAAF1" rx="58"
                        transform="rotate(13 159.042 50.663)" />
                    <path class="blue" fill="#5DAAF1" d="m164.305 126 248.242 57.311-16.646 72.104-248.242-57.312z" />
                    <path class="blue" fill="#5DAAF1"
                        d="M377 159h40v92h-40zM70 102.825 141.012 45l77.642 95.347-71.012 57.826z" />
                    <path class="blue" fill="#5DAAF1" d="m151.638 49.079 112.866 26.057-15.971 69.18-112.866-26.057z" />
                    <path class="blue" fill="#5DAAF1"
                        d="m147.622 46.516 28.984 9.675-22.482 67.347-28.984-9.675zm236.164 192.862h33.319v67.92h-33.319zm0 67.92v-75.609L362 224l21.786 83.298Zm-245.189-29.614 35.092-92.309-23.029-19.498-12.063 111.807ZM174 283.5l12.562-106.137 29.393-6.821L174 283.5Z" />
                    <path class="blue" fill="#5DAAF1" d="M200.701 113.82 174 283.5l-35.229-6.32 61.93-163.36Z" />
                    <path class="purple" fill="#A770EA"
                        d="m103.459 155.41-48.84 70.804 15.787 23.485 63.822-54.251-30.769-40.038Zm199.156 108.147h28.844v36.191h-28.844z" />
                    <path class="purple" fill="#A770EA" d="m302.615 299.748 28.407-52.007L293 239l9.615 60.748Z" />
                    <path class="purple" fill="#A770EA" d="m331.459 299.748 20.541-47.2-40.207-9.178 19.666 56.378Z" />
                    <path class="blue" fill="#5DAAF1"
                        d="M590.18 307H523.3v-30.4h17.86V71.02H523.3V41h79.8c18.24 0 35.467 3.167 51.68 9.5 16.213 6.08 30.4 14.947 42.56 26.6 12.16 11.653 21.787 25.713 28.88 42.18 7.093 16.213 10.64 34.58 10.64 55.1 0 14.947-2.66 30.273-7.98 45.98-5.067 15.707-13.427 29.893-25.08 42.56-11.653 12.92-26.853 23.56-45.6 31.92-18.493 8.107-41.167 12.16-68.02 12.16ZM572.7 71.02V276.6h26.6c14.947 0 28.88-2.407 41.8-7.22 12.92-4.813 24.193-11.78 33.82-20.9 9.373-8.867 16.72-19.507 22.04-31.92 5.573-12.667 8.36-26.853 8.36-42.56s-2.787-29.893-8.36-42.56c-5.32-12.667-12.667-23.56-22.04-32.68-9.627-8.867-20.9-15.707-33.82-20.52-12.92-4.813-26.853-7.22-41.8-7.22h-26.6Zm266.698 120.84c-7.094 0-13.554 1.267-19.38 3.8-5.574 2.28-10.387 5.573-14.44 9.88-3.04 3.547-5.574 7.6-7.6 12.16-1.774 4.56-2.787 9.5-3.04 14.82a5454.18 5454.18 0 0 0 35.34-12.92 2039.524 2039.524 0 0 1 35.72-13.3c-3.547-4.307-7.6-7.727-12.16-10.26-4.307-2.787-9.12-4.18-14.44-4.18Zm48.26 98.42c-6.334 6.333-13.554 11.273-21.66 14.82-8.107 3.547-16.974 5.32-26.6 5.32-10.64 0-20.647-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.287-14.693-16.34-23.56c-3.8-9.12-5.7-18.873-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.053-9.12 9.5-17.1 16.34-23.94 6.84-6.587 14.82-11.78 23.94-15.58 9.373-4.053 19.38-6.08 30.02-6.08 7.853 0 15.326 1.647 22.42 4.94 7.346 3.04 13.933 7.347 19.76 12.92 5.573 5.573 10.513 12.287 14.82 20.14 4.306 7.6 7.6 15.96 9.88 25.08l-51.68 19a11397.596 11397.596 0 0 1-51.3 19c3.8 5.32 8.74 9.627 14.82 12.92 6.333 3.04 13.426 4.56 21.28 4.56 5.826 0 11.146-1.013 15.96-3.04 4.813-2.027 9.12-5.067 12.92-9.12l19.38 22.8ZM1115.73 307h-56.62v-15.2c-.25.76-1.52 2.153-3.8 4.18-2.28 2.027-5.44 4.053-9.5 6.08-4.3 2.28-9.37 4.18-15.2 5.7-5.82 1.773-12.41 2.66-19.76 2.66-10.64 0-20.645-1.9-30.018-5.7-9.373-4.053-17.48-9.5-24.32-16.34s-12.287-14.82-16.34-23.94c-3.8-9.12-5.7-18.747-5.7-28.88s1.9-19.633 5.7-28.5c4.053-9.12 9.5-17.1 16.34-23.94s14.947-12.16 24.32-15.96c9.373-4.053 19.378-6.08 30.018-6.08 6.34 0 12.29.887 17.86 2.66 5.83 1.773 10.9 3.8 15.2 6.08 4.31 2.28 7.35 4.18 9.12 5.7 1.78 1.267 2.92 2.28 3.42 3.04-.5-2.027-.88-4.56-1.14-7.6V52.02h-25.08V22h56.62v254.98h28.88V307Zm-104.88-115.14c-6.58 0-12.665 1.14-18.238 3.42-5.573 2.28-10.387 5.32-14.44 9.12-3.547 4.053-6.46 8.74-8.74 14.06-2.027 5.067-3.04 10.767-3.04 17.1 0 6.587 1.267 12.793 3.8 18.62 2.533 5.827 5.953 10.64 10.26 14.44 3.8 3.547 8.233 6.333 13.3 8.36 5.32 1.773 11.018 2.66 17.098 2.66 6.08 0 11.66-.887 16.72-2.66 5.07-2.027 9.63-4.813 13.68-8.36 4.31-3.8 7.73-8.613 10.26-14.44 2.54-5.827 3.8-12.033 3.8-18.62 0-7.093-1.39-13.553-4.18-19.38-2.53-5.827-6.08-10.64-10.64-14.44-3.8-3.04-8.23-5.447-13.3-7.22-5.06-1.773-10.51-2.66-16.34-2.66Zm267.47 78.66c-5.06 12.16-13.3 21.913-24.7 29.26-11.14 7.093-23.56 10.64-37.24 10.64-14.94 0-26.72-3.927-35.34-11.78-8.61-7.853-13.17-18.113-13.68-30.78v-73.34h-25.08V164.5h56.62v88.92c.51 6.84 2.92 12.793 7.22 17.86 4.56 4.813 11.66 7.473 21.28 7.98 6.59 0 12.8-1.14 18.62-3.42 6.08-2.28 11.4-5.447 15.96-9.5 4.56-4.053 8.24-8.867 11.02-14.44 2.79-5.573 4.18-11.653 4.18-18.24v-39.14h-25.08V164.5h56.62v115.9h23.56V307h-55.1v-19.38l1.14-17.1Zm204.18 23.56c-6.58 5.067-13.93 9.12-22.04 12.16-7.85 2.787-16.34 4.18-25.46 4.18-10.64 0-20.64-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.28-14.693-16.34-23.56c-3.8-8.867-5.7-18.62-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.06-9.12 9.5-16.973 16.34-23.56 6.84-6.84 14.82-12.16 23.94-15.96 9.38-4.053 19.38-6.08 30.02-6.08 9.38 0 18.12 1.52 26.22 4.56 8.11 2.787 15.46 6.713 22.04 11.78v44.08h-28.12v-25.46c-3.04-1.52-6.33-2.533-9.88-3.04-3.29-.76-6.71-1.14-10.26-1.14-6.08 0-11.78 1.013-17.1 3.04-5.06 1.773-9.5 4.307-13.3 7.6-4.56 4.053-8.1 8.867-10.64 14.44-2.28 5.573-3.42 11.78-3.42 18.62 0 6.333 1.14 12.287 3.42 17.86 2.28 5.573 5.45 10.387 9.5 14.44 4.06 3.547 8.74 6.46 14.06 8.74 5.32 2.027 11.15 3.04 17.48 3.04 5.58 0 10.64-.76 15.2-2.28 4.82-1.52 9.25-3.927 13.3-7.22l19 23.94Zm103.54-102.22c-7.1 0-13.56 1.267-19.38 3.8-5.58 2.28-10.39 5.573-14.44 9.88-3.04 3.547-5.58 7.6-7.6 12.16-1.78 4.56-2.79 9.5-3.04 14.82a5726.9 5726.9 0 0 0 35.34-12.92c11.9-4.56 23.81-8.993 35.72-13.3-3.55-4.307-7.6-7.727-12.16-10.26-4.31-2.787-9.12-4.18-14.44-4.18Zm48.26 98.42c-6.34 6.333-13.56 11.273-21.66 14.82-8.11 3.547-16.98 5.32-26.6 5.32-10.64 0-20.65-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.29-14.693-16.34-23.56c-3.8-9.12-5.7-18.873-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.05-9.12 9.5-17.1 16.34-23.94 6.84-6.587 14.82-11.78 23.94-15.58 9.37-4.053 19.38-6.08 30.02-6.08 7.85 0 15.32 1.647 22.42 4.94 7.34 3.04 13.93 7.347 19.76 12.92 5.57 5.573 10.51 12.287 14.82 20.14 4.3 7.6 7.6 15.96 9.88 25.08-17.23 6.333-34.46 12.667-51.68 19-16.98 6.333-34.08 12.667-51.3 19 3.8 5.32 8.74 9.627 14.82 12.92 6.33 3.04 13.42 4.56 21.28 4.56 5.82 0 11.14-1.013 15.96-3.04 4.81-2.027 9.12-5.067 12.92-9.12l19.38 22.8Z" />
                </svg>
            </a>
            <div class="nav-links">
                <a class="mobile link-btn" id="nav-toggle"><i class="fa-solid fa-bars"></i></a>
                <div id="link-list" class="hide">
                    <a class="link-btn" href="./getting-started.html">Get Started</a>
                    <a class="link-btn" href="./reference.html">Reference</a>
                    <a class="link-btn" href="./sandbox.html">Live Code</a>
                </div>
            </div>
        </nav>
'''

conclusion = '''
        <footer>
            <a class="nav-logo" href="../index.html">
                <svg xmlns="http://www.w3.org/2000/svg" width="1668" height="402" fill="none" viewBox="0 0 1668 402">
                    <ellipse class="blue" cx="52.954" cy="86.34" fill="#5DAAF1" rx="42.5" ry="46"
                        transform="rotate(14.995 52.954 86.34)" />
                    <path class="blue" fill="#5DAAF1" d="m64.373 41.777 35.74 9.573-23.804 88.867-35.74-9.573z" />
                    <rect class="blue" width="89" height="109" x="79.397" y="28.202" fill="#5DAAF1" rx="26"
                        transform="rotate(14.995 79.397 28.202)" />
                    <rect class="blue" width="88" height="109" x="104.511" y="34.929" fill="#5DAAF1" rx="41"
                        transform="rotate(14.995 104.511 34.929)" />
                    <circle cx="102.759" cy="57.343" r="7.5" fill="#fff" transform="rotate(14.995 102.759 57.343)" />
                    <path class="blue" fill="#5DAAF1"
                        d="M138.713 51.92c-.708-2.633-.535-9.472 5.812-15.768 7.934-7.87 13.773-2.974 9.545 5.889-3.382 7.09-7.816 15.009-9.61 18.082l-5.747-8.203Z" />
                    <rect class="blue" width="277" height="144.529" x="159.042" y="50.663" fill="#5DAAF1" rx="58"
                        transform="rotate(13 159.042 50.663)" />
                    <path class="blue" fill="#5DAAF1" d="m164.305 126 248.242 57.311-16.646 72.104-248.242-57.312z" />
                    <path class="blue" fill="#5DAAF1"
                        d="M377 159h40v92h-40zM70 102.825 141.012 45l77.642 95.347-71.012 57.826z" />
                    <path class="blue" fill="#5DAAF1" d="m151.638 49.079 112.866 26.057-15.971 69.18-112.866-26.057z" />
                    <path class="blue" fill="#5DAAF1"
                        d="m147.622 46.516 28.984 9.675-22.482 67.347-28.984-9.675zm236.164 192.862h33.319v67.92h-33.319zm0 67.92v-75.609L362 224l21.786 83.298Zm-245.189-29.614 35.092-92.309-23.029-19.498-12.063 111.807ZM174 283.5l12.562-106.137 29.393-6.821L174 283.5Z" />
                    <path class="blue" fill="#5DAAF1" d="M200.701 113.82 174 283.5l-35.229-6.32 61.93-163.36Z" />
                    <path class="purple" fill="#A770EA"
                        d="m103.459 155.41-48.84 70.804 15.787 23.485 63.822-54.251-30.769-40.038Zm199.156 108.147h28.844v36.191h-28.844z" />
                    <path class="purple" fill="#A770EA" d="m302.615 299.748 28.407-52.007L293 239l9.615 60.748Z" />
                    <path class="purple" fill="#A770EA" d="m331.459 299.748 20.541-47.2-40.207-9.178 19.666 56.378Z" />
                    <path class="blue" fill="#5DAAF1"
                        d="M590.18 307H523.3v-30.4h17.86V71.02H523.3V41h79.8c18.24 0 35.467 3.167 51.68 9.5 16.213 6.08 30.4 14.947 42.56 26.6 12.16 11.653 21.787 25.713 28.88 42.18 7.093 16.213 10.64 34.58 10.64 55.1 0 14.947-2.66 30.273-7.98 45.98-5.067 15.707-13.427 29.893-25.08 42.56-11.653 12.92-26.853 23.56-45.6 31.92-18.493 8.107-41.167 12.16-68.02 12.16ZM572.7 71.02V276.6h26.6c14.947 0 28.88-2.407 41.8-7.22 12.92-4.813 24.193-11.78 33.82-20.9 9.373-8.867 16.72-19.507 22.04-31.92 5.573-12.667 8.36-26.853 8.36-42.56s-2.787-29.893-8.36-42.56c-5.32-12.667-12.667-23.56-22.04-32.68-9.627-8.867-20.9-15.707-33.82-20.52-12.92-4.813-26.853-7.22-41.8-7.22h-26.6Zm266.698 120.84c-7.094 0-13.554 1.267-19.38 3.8-5.574 2.28-10.387 5.573-14.44 9.88-3.04 3.547-5.574 7.6-7.6 12.16-1.774 4.56-2.787 9.5-3.04 14.82a5454.18 5454.18 0 0 0 35.34-12.92 2039.524 2039.524 0 0 1 35.72-13.3c-3.547-4.307-7.6-7.727-12.16-10.26-4.307-2.787-9.12-4.18-14.44-4.18Zm48.26 98.42c-6.334 6.333-13.554 11.273-21.66 14.82-8.107 3.547-16.974 5.32-26.6 5.32-10.64 0-20.647-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.287-14.693-16.34-23.56c-3.8-9.12-5.7-18.873-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.053-9.12 9.5-17.1 16.34-23.94 6.84-6.587 14.82-11.78 23.94-15.58 9.373-4.053 19.38-6.08 30.02-6.08 7.853 0 15.326 1.647 22.42 4.94 7.346 3.04 13.933 7.347 19.76 12.92 5.573 5.573 10.513 12.287 14.82 20.14 4.306 7.6 7.6 15.96 9.88 25.08l-51.68 19a11397.596 11397.596 0 0 1-51.3 19c3.8 5.32 8.74 9.627 14.82 12.92 6.333 3.04 13.426 4.56 21.28 4.56 5.826 0 11.146-1.013 15.96-3.04 4.813-2.027 9.12-5.067 12.92-9.12l19.38 22.8ZM1115.73 307h-56.62v-15.2c-.25.76-1.52 2.153-3.8 4.18-2.28 2.027-5.44 4.053-9.5 6.08-4.3 2.28-9.37 4.18-15.2 5.7-5.82 1.773-12.41 2.66-19.76 2.66-10.64 0-20.645-1.9-30.018-5.7-9.373-4.053-17.48-9.5-24.32-16.34s-12.287-14.82-16.34-23.94c-3.8-9.12-5.7-18.747-5.7-28.88s1.9-19.633 5.7-28.5c4.053-9.12 9.5-17.1 16.34-23.94s14.947-12.16 24.32-15.96c9.373-4.053 19.378-6.08 30.018-6.08 6.34 0 12.29.887 17.86 2.66 5.83 1.773 10.9 3.8 15.2 6.08 4.31 2.28 7.35 4.18 9.12 5.7 1.78 1.267 2.92 2.28 3.42 3.04-.5-2.027-.88-4.56-1.14-7.6V52.02h-25.08V22h56.62v254.98h28.88V307Zm-104.88-115.14c-6.58 0-12.665 1.14-18.238 3.42-5.573 2.28-10.387 5.32-14.44 9.12-3.547 4.053-6.46 8.74-8.74 14.06-2.027 5.067-3.04 10.767-3.04 17.1 0 6.587 1.267 12.793 3.8 18.62 2.533 5.827 5.953 10.64 10.26 14.44 3.8 3.547 8.233 6.333 13.3 8.36 5.32 1.773 11.018 2.66 17.098 2.66 6.08 0 11.66-.887 16.72-2.66 5.07-2.027 9.63-4.813 13.68-8.36 4.31-3.8 7.73-8.613 10.26-14.44 2.54-5.827 3.8-12.033 3.8-18.62 0-7.093-1.39-13.553-4.18-19.38-2.53-5.827-6.08-10.64-10.64-14.44-3.8-3.04-8.23-5.447-13.3-7.22-5.06-1.773-10.51-2.66-16.34-2.66Zm267.47 78.66c-5.06 12.16-13.3 21.913-24.7 29.26-11.14 7.093-23.56 10.64-37.24 10.64-14.94 0-26.72-3.927-35.34-11.78-8.61-7.853-13.17-18.113-13.68-30.78v-73.34h-25.08V164.5h56.62v88.92c.51 6.84 2.92 12.793 7.22 17.86 4.56 4.813 11.66 7.473 21.28 7.98 6.59 0 12.8-1.14 18.62-3.42 6.08-2.28 11.4-5.447 15.96-9.5 4.56-4.053 8.24-8.867 11.02-14.44 2.79-5.573 4.18-11.653 4.18-18.24v-39.14h-25.08V164.5h56.62v115.9h23.56V307h-55.1v-19.38l1.14-17.1Zm204.18 23.56c-6.58 5.067-13.93 9.12-22.04 12.16-7.85 2.787-16.34 4.18-25.46 4.18-10.64 0-20.64-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.28-14.693-16.34-23.56c-3.8-8.867-5.7-18.62-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.06-9.12 9.5-16.973 16.34-23.56 6.84-6.84 14.82-12.16 23.94-15.96 9.38-4.053 19.38-6.08 30.02-6.08 9.38 0 18.12 1.52 26.22 4.56 8.11 2.787 15.46 6.713 22.04 11.78v44.08h-28.12v-25.46c-3.04-1.52-6.33-2.533-9.88-3.04-3.29-.76-6.71-1.14-10.26-1.14-6.08 0-11.78 1.013-17.1 3.04-5.06 1.773-9.5 4.307-13.3 7.6-4.56 4.053-8.1 8.867-10.64 14.44-2.28 5.573-3.42 11.78-3.42 18.62 0 6.333 1.14 12.287 3.42 17.86 2.28 5.573 5.45 10.387 9.5 14.44 4.06 3.547 8.74 6.46 14.06 8.74 5.32 2.027 11.15 3.04 17.48 3.04 5.58 0 10.64-.76 15.2-2.28 4.82-1.52 9.25-3.927 13.3-7.22l19 23.94Zm103.54-102.22c-7.1 0-13.56 1.267-19.38 3.8-5.58 2.28-10.39 5.573-14.44 9.88-3.04 3.547-5.58 7.6-7.6 12.16-1.78 4.56-2.79 9.5-3.04 14.82a5726.9 5726.9 0 0 0 35.34-12.92c11.9-4.56 23.81-8.993 35.72-13.3-3.55-4.307-7.6-7.727-12.16-10.26-4.31-2.787-9.12-4.18-14.44-4.18Zm48.26 98.42c-6.34 6.333-13.56 11.273-21.66 14.82-8.11 3.547-16.98 5.32-26.6 5.32-10.64 0-20.65-1.9-30.02-5.7-9.12-4.053-17.1-9.5-23.94-16.34s-12.29-14.693-16.34-23.56c-3.8-9.12-5.7-18.873-5.7-29.26 0-10.133 1.9-19.76 5.7-28.88 4.05-9.12 9.5-17.1 16.34-23.94 6.84-6.587 14.82-11.78 23.94-15.58 9.37-4.053 19.38-6.08 30.02-6.08 7.85 0 15.32 1.647 22.42 4.94 7.34 3.04 13.93 7.347 19.76 12.92 5.57 5.573 10.51 12.287 14.82 20.14 4.3 7.6 7.6 15.96 9.88 25.08-17.23 6.333-34.46 12.667-51.68 19-16.98 6.333-34.08 12.667-51.3 19 3.8 5.32 8.74 9.627 14.82 12.92 6.33 3.04 13.42 4.56 21.28 4.56 5.82 0 11.14-1.013 15.96-3.04 4.81-2.027 9.12-5.067 12.92-9.12l19.38 22.8Z" />
                </svg>
            </a>
            <div class="footer-links">
                <div class="footer-col">
                    <a href="./getting-started.html">Get Started</a>
                    <a href="./sandbox.html">Live Code</a>
                    <a href="https://github.com/jsiek/deduce" target="_blank">Source Code</a>
                    <a href="https://github.com/HalflingHelper/deduce-mode" target="_blank">VS-Code deduce-mode</a>
                    <a href="https://github.com/mateidragony/deduce-mode" target="_blank">Emacs deduce-mode</a>
                </div>
                <div class="footer-col">
                    <a href="./reference.html">Reference</a>
                    <a href="./cheat-sheet.html">Cheat sheet</a>
                    <a href="./deduce-programming.html">Programming in deduce</a>
                    <a href="./deduce-proofs.html">Proofs in deduce</a>
                </div>
                <div class="footer-col">
                    <a href="./syntax.html">Syntax/Grammar</a>
                    <a href="./syntax.html#statements">Statements</a>
                    <a href="./syntax.html#proofs">Proofs</a>
                    <a href="./syntax.html#terms">Terms</a>
                    <a href="./syntax.html#types">Types</a>
                    <a href="./syntax.html#unicode">Deduce unicode</a>
                </div>
            </div>
        </footer>
    </div>


    <script src="../js/cache.js"></script>
    <script src="../js/script.js"></script>
    <script src="../js/code.js"></script>
    <script src="../js/codeUtils.js"></script>
</body>

</html>
'''


def convertFile(fname):
    with open(f'./doc/{fname}.md', 'r') as f:
        text = f.read()
        html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'toc', CodeExtension(fname)])
        # Post postprocessing
        html = html.replace("&amp;", "&")

    with open(f'./gh-pages/pages/{mdToHtmlName[fname]}.html', 'w') as f:
        f.write(prelude(fname))
        f.write(html)
        f.write(conclusion)


if __name__ == "__main__":
    # convert all md files in the doc directory
    doc_dir = "./doc/"
    for f in [f for f in listdir(doc_dir) if isfile(join(doc_dir, f))]:
        m = re.search(r'(.*).md', f)
        if m: 
            convertFile(m.group(1))