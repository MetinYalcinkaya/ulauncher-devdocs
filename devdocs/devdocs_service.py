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

        docs = self.python_version_fallback(docs)
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

    def python_version_fallback(self, docs_to_fetch):
      """
      If 'python' is present in docs_to_fetch (without version),
      automatically replace it with the highest python~X.Y version from devdocs
      """
      r = requests.get(DEVDOCS_INDEX_ALL_URL)
      all_docs = r.json()

      python_slugs = [d['slug'] for d in all_docs if d['slug'].startswith('python~')]

      if not python_slugs:
        return docs_to_fetch

      version_regex = re.compile(r'python~(\d+\.\d+)')
      versions = []
      for slug in python_slugs:
        match = version_regex.match(slug)
        if match:
          major_minor_str = match.group(1)
          major_str, minor_str = major_minor_str.split('.')
          major = int(major_str)
          minor = int(minor_str)
          versions.append((major, minor))
      if not versions:
        return docs_to_fetch

      versions.sort()
      (latest_major, latest_minor) = versions[-1]
      latest_python_slug = f"python~{latest_major}.{latest_minor}"

      new_docs_to_fetch = []
      for slug in docs_to_fetch:
        if slug == "python":
          new_docs_to_fetch.append(latest_python_slug)
        else:
          new_docs_to_fetch.append(slug)
      return new_docs_to_fetch
