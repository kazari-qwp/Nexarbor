"""Heuristic page-heading metadata; does not build an index."""
import re

class StructureTracker:

    def __init__(self):
        self.part = 'front_matter'
        self.part_title = 'Front matter'
        self.chapter = self.chapter_title = None
        self.section = self.section_title = None

    def update(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first = lines[0] if lines else ''
        chapter = re.match('^CHAPTER\\s+([IVXLCDM]+)\\s*\\n([^\\n]+)', text)
        appendix = re.match('^(?:APPENDIX|Appendix)\\s+([A-Z])(?:[ \\t]*\\n|[ \\t]+)([^\\n]+)', text)
        named = {'Preface': 'front_matter', 'Contents': 'front_matter', 'Introduction': 'front_matter', 'Suggestions for Further Reading': 'front_matter', 'Bibliography': 'back_matter', 'Results from Algebra': 'back_matter', 'Glossary of Notations': 'back_matter', 'Index': 'back_matter'}
        if chapter:
            self.part, self.chapter, self.chapter_title = ('chapter', chapter.group(1), chapter.group(2).strip())
            self.part_title = self.chapter_title
            self.section = self.section_title = None
        elif appendix:
            identifier, title = ('Appendix ' + appendix.group(1), appendix.group(2).strip())
            if self.chapter != identifier:
                self.section = self.section_title = None
            self.part, self.chapter, self.chapter_title, self.part_title = ('appendix', identifier, title, title)
        elif first in named:
            self.part, self.part_title = (named[first], first)
            self.chapter = self.chapter_title = self.section = self.section_title = None
        if self.part in ('chapter', 'appendix') and (not chapter) and (not appendix):
            for line in lines[:2]:
                section = re.fullmatch("([1-9]\\d?)\\s+([A-Za-z][A-Za-z0-9 ,?()'/:;\\-]{2,90})", line)
                if section:
                    self.section, self.section_title = (section.group(1), section.group(2).strip())
                    break
        return {'part': self.part, 'part_title': self.part_title, 'chapter': self.chapter, 'chapter_title': self.chapter_title, 'section': self.section, 'section_title': self.section_title, 'structure_method': 'page_headings'}
