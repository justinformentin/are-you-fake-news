""" 
This module gets called by the web app each time a site is requested. 

It orchestrates much of the user facing data processing including:
    * Checking for a valid web address
    * Spidering target site for article urls
    * Sending each article URL to a article scraping lambda to get text
    * Sending the accumulated text to the NLP lambda
    * Activating the plotting function to plot the NLP results

"""
import hashlib
import json
import os
from itertools import islice
from multiprocessing import dummy
from pprint import pprint
from time import sleep, time

import newspaper
import requests
import mongo_query_results
import textblob
from unidecode import unidecode

from helpers import addDict, timeit
from plotter import plot

nlp_api = 'https://lbs45qdjea.execute-api.us-west-2.amazonaws.com/dev/dev_dnn_nlp'
scrape_articles_api = 'https://lbs45qdjea.execute-api.us-west-2.amazonaws.com/dev/scraper'
meta_scraper = 'https://lbs45qdjea.execute-api.us-west-2.amazonaws.com/dev/meta_scraper'

test = False


class LambdaWhisperer:
    json_results = []

    def __init__(self):
        pass

    @timeit
    def scrape_api_endpoint(self, url_: str):
        response = json.loads(requests.put(scrape_api, data=url_).text)

        if 'message' in response:
            return None

        return {url_: response}

    @timeit
    def nlp_api_endpoint(self, url_text: dict, url: str):
        # json.dump(url_text, open('./latest.json', 'w'))

        response = json.loads(requests.put(nlp_api, json=url_text).text)

        mongo_query_results.insert(response, url)
        LambdaWhisperer.json_results, n_articles = mongo_query_results.get_scores(url)
        return n_articles


class Titles:
    collect = []


class GetSite:

    def __init__(self, url, name_clean=None):
        self.API = LambdaWhisperer()

        self.url = url
        if not name_clean:
            self.name_clean = self.strip()
        else:
            self.name_clean = name_clean
        self.hash = self.name_clean + '_' + hashlib.md5(str(time()).encode('utf-8')).hexdigest()[:5]

    def run(self):
        if not self.url:
            return False
        if self.url == 'ConnectionError':
            return self.url
        # Get list of newspaper.Article objs
        self.article_objs = self.get_newspaper()

        if self.article_objs in ["No articles found!", "Empty list"]:
            try:
                LambdaWhisperer.json_results, self.num_articles = mongo_query_results.get_scores(
                    self.url)
            except IndexError:
                return 'ConnectionError'
        else:
            # Threadpool for getting articles

            self.articles = self.articles_gen()
            self.num_articles = self.API.nlp_api_endpoint(self.articles, self.url)

        if self.API.json_results:
            self.dump()
            self.save_plot()

        print(sorted(self.API.json_results.items(), key=lambda kv: kv[1], reverse=True))
        print(self.url)

        return self.num_articles, 0, 0, self.num_articles, self.hash

    def save_plot(self):
        plot(url=self.url, name_clean=self.hash)

    @timeit
    def articles_gen(self):
        urls = eval(self.article_objs)[:100]

        res = json.loads(requests.put(meta_scraper, json=urls).text)

        return res

    def strip(self):
        return ''.join([
            c for c in self.url.replace('https://', '').replace('http://', '').replace('www.', '')
            if c.isalpha()
        ])

    def dump(self):

        j_path = './static/{}.json'.format(self.hash)
        with open(j_path, 'w') as fp:
            print(LambdaWhisperer.json_results)

            json.dump(LambdaWhisperer.json_results, fp, sort_keys=True)

    @timeit
    def get_newspaper(self):

        return requests.put(scrape_articles_api, self.url).text


if __name__ == '__main__':
    test = False

    @timeit
    def run(url, sample_articles=None):
        GetSite(url, sample_articles).run()

    run('naturalnews.com')
