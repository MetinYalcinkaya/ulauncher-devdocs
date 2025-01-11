""" DevDocs Module """
import json
import os
import time
import difflib
import re

import requests

DEVDOCS_BASE_URL = 'https://devdocs.io'

DEVDOCS_INDEX_ALL_URL = 'https://devdocs.io/docs/docs.json'

DEVDOCS_DOC_ENTRIES_URL = 'https://devdocs.io/docs/%slug%/index.json'


class DevDocsService():
    """ Service that handles everything related with devdocs """

    def __init__(self, logger, cache_dir):
        """ Constructor method """
        self.logger = logger
        self.cache_dir = cache_dir
        self.index_file = os.path.join(self.cache_dir, "index.json")
        self.entries_dir = os.path.join(self.cache_dir, "entries")
        self.docs_to_fetch = []

        self.ensure_cache_dirs()

    @staticmethod
    def get_base_url():
        """ Returns the DevDocs base url """
        return DEVDOCS_BASE_URL

    @staticmethod
    def get_index_cache_ttl():
        """ Returns the cache ttl """
        return 86400

    def ensure_cache_dirs(self):
        """ Creates all the necessary directories and files """

        # Creates the main "cache" dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        # creates the main "index" file if it doesnt exist yet.
        if not os.path.exists(self.index_file):
            with open(self.index_file, 'w') as f:
                json.dump([], f)

        # creates the directory to save the entries.
        if not os.path.isdir(self.entries_dir):
            os.mkdir(self.entries_dir, 0o755)

    def set_docs_to_fetch(self, docs):
        """ Sets the list of docs that we want to fetch """
        if isinstance(docs, str):
          try:
            docs = json.loads(docs)
          except:
            docs = []

        docs = self.version_fallback(docs)
        self.docs_to_fetch = docs

    def index(self):
        """ Fetch Documentation from DevDocs website """

        self.logger.info("Start indexing documentation")

        # 1. Fetch the available documentation from DevDocs website.
        r = requests.get(DEVDOCS_INDEX_ALL_URL)
        docs = r.json()

        docs = [x for x in docs if x['slug'] in self.docs_to_fetch]

        with open(os.path.join(self.index_file), 'w') as f:
            json.dump(docs, f)

        # For each doc fetch its associated entries.
        for doc in docs:
            self.fetch_doc_entries(doc['slug'])
            time.sleep(0.5)

        self.logger.info("Index Finished")

    def fetch_doc_entries(self, doc):
        """ Fetch all the entries from a single Dcoumentation """

        self.logger.info("Fetching Docs for %s " % doc)

        url = DEVDOCS_DOC_ENTRIES_URL.replace("%slug%", doc)
        r = requests.get(url)

        entries = r.json()

        with open(os.path.join(self.entries_dir, doc + '.json'), 'w') as f:
            json.dump(entries, f)

    def get_docs(self, query=None):
        """ Returns the list of available documentation """

        with open(self.index_file, 'r') as f:
            data = json.load(f)

        if query:
            data = [
                x for x in data if query.strip().lower() in x['name'].lower()
            ]

        return data

    def get_doc_entries(self, lang_slug, query=""):
        """ Returns a list of entries associated with a respective language """

        entries_file = os.path.join(self.entries_dir, lang_slug + ".json")

        if not os.path.exists(entries_file):
            return []

        with open(entries_file, 'r') as f:
            data = json.load(f)

        entries = data['entries']
        if query:
            entries = [
                x for x in entries
                if query.strip().lower() in x['name'].lower()
            ]

            # Apply some stuff to get results with more relevance.
            # @see https://stackoverflow.com/questions/17903706/how-to-sort-list-of-strings-by-best-match-difflib-ratio
            entries = sorted(entries,
                             key=lambda x: difflib.SequenceMatcher(
                                 None, x['name'], query).ratio(),
                             reverse=True)

        return entries

    def get_doc_by_slug(self, doc_slug):
        """ Returns the documentation details based on a slug """
        with open(self.index_file, 'r') as f:
            data = json.load(f)

        for doc in data:
            if doc_slug == doc['slug']:
                return doc

        return None

    def parse_version_to_tuple(self, version_str):
      """
      Parses version string (3.10 or 4.1.2) in to a tuple of ints for easy sorting
      If segment can't be converted to an int (such as 'beta'), fallback to 0 or handle specially
      """
      parts = []
      for part in version_str.split('.'):
        try:
          parts.append(int(part))
        except ValueError:
          parts.append(0)
      return tuple(parts)

    def version_fallback(self, docs_to_fetch):
      """
      For any doc name in docs_to_fetch that doesn't contain '~' (unversioned),
      find if DevDocs has one or more versioned docs that start with that base name + '~'.
      Default to highest version among them
      """
      r = requests.get(DEVDOCS_INDEX_ALL_URL)
      all_docs = r.json()

      base_map = {}
      pattern = re.compile(r'^(.+?)~(.+)$')
      for doc in all_docs:
        slug = doc['slug']
        match = pattern.match(slug)
        if match:
          base_name = match.group(1)
          base_map.setdefault(base_name, []).append(slug)
      for base, slugs in base_map.items():
        slug_version_pairs = []
        for s in slugs:
          version_part = s.split('~', 1)[1]
          slug_version_pairs.append((s, self.parse_version_to_tuple(version_part)))
        slug_version_pairs.sort(key=lambda x: x[1])
        base_map[base] = [p[0] for p in slug_version_pairs]
      new_docs = []
      for doc in docs_to_fetch:
        if '~' in doc:
          new_docs.append(doc)
        else:
          if doc in base_map:
            highest_versioned_slug = base_map[doc][-1]
            new_docs.append(highest_versioned_slug)
          else:
            new_docs.append(doc)

      return new_docs
