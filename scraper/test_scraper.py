import unittest
import scraper
import process_resources
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scraper')
logger.setLevel(logging.INFO)

class TestScraper(unittest.TestCase):
    def test_link_1(self):
        result = scraper.scrape("http://news.zing.vn/nhip-song-tre/thay-giao-gay-sot-tung-bo-luat-tinh-yeu/a291427.html")
        print process_resources.extract_clean_content(result['htmlContent'])
        self.assertFalse(result.get('unscrapable'))
    def test_link_2(self):
        result = scraper.scrape("http://news.google.com/news/url?sa=t&fd=R&usg=AFQjCNErKUuDda2EHlPu0LwpUJ0dcdDY4g&url=http://focus.stockstar.com/SS2012101000003737.shtml")
        print process_resources.extract_clean_content(result['htmlContent'])
        self.assertFalse(result.get('unscrapable'))
    def test_link_3(self):
        result = scraper.scrape("http://www.theargus.co.uk/news/9845086.Screening_follows_new_cases_of_TB_reported_in_Sussex/")
        print process_resources.extract_clean_content(result['htmlContent'])
        self.assertFalse(result.get('unscrapable'))
    def test_link_4(self):
        result = scraper.scrape("http://www.foodmate.net/news/yujing/2012/05/206413.html")
        print process_resources.extract_clean_content(result['htmlContent'])
        self.assertFalse(result.get('unscrapable'))
