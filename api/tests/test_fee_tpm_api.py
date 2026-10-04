import sqlite3
import tempfile
import unittest
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from api.server import NotFoundError, make_handler, query_fee_tpm_activities, query_fee_tpm_issues, query_fee_tpm_settlements


DDL = Path(__file__).resolve().parents[2] / 'mvp' / 'ddl' / 'ec101_mvp_sqlite.sql'


class FeeTpmQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'fee.db'
        con = sqlite3.connect(self.path)
        con.executescript(DDL.read_text(encoding='utf-8'))
        con.execute("INSERT INTO dealer_platform(dealer_name,platform_name) VALUES ('经销商','平台')")
        con.execute("INSERT INTO tpm_application(tpm_code,apply_amount,budget_reserve_no,fee_pay_dept) VALUES ('TPM-1',1000,'B-1','市场部')")
        con.execute("INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promotion_type,start_time,end_time,rule_version) VALUES (1,1,'金额活动','非券类','满减','2026-01-01','2026-12-31','v1')")
        con.execute("INSERT INTO activity(dealer_platform_id,activity_name,activity_category,promotion_type,start_time,end_time,rule_version) VALUES (1,'赠品活动','非券类','立赠','2026-01-01','2026-12-31','v1')")
        con.execute("INSERT INTO result_calc_batch(calc_batch_id,calc_date,rule_version) VALUES (1,'2026-10-01','v1')")
        con.execute("INSERT INTO result_calc_batch(calc_batch_id,calc_date,rule_version) VALUES (2,'2026-10-02','v2')")
        con.execute("INSERT INTO order_header(dealer_platform_id,order_no,order_time,order_status) VALUES (1,'O-money','2026-10-01','已完成')")
        con.execute("INSERT INTO order_header(dealer_platform_id,order_no,order_time,order_status) VALUES (1,'O-gift','2026-10-01','已完成')")
        con.execute("INSERT INTO order_activity(order_id,activity_id,activity_product_amount) VALUES (1,1,100)")
        con.execute("INSERT INTO order_activity(order_id,activity_id,activity_product_amount) VALUES (2,2,100)")
        for batch, amount in ((1, 10), (2, 20)):
            con.execute("INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,consistency,calc_batch_id) VALUES (1,?,?, '一致',?)", (amount, amount, batch))
            con.execute("INSERT INTO result_release_candidate(order_id,calc_date,is_candidate,reason,calc_batch_id) VALUES (1,'2026-10-02',1,'T-2',?)", (batch,))
            con.execute("INSERT INTO result_fee(tpm_id,activity_id,actual_discount_total,budget_amount,diff_amount,settle_amount,settle_status,calc_batch_id) VALUES (1,1,?,1000,980,?,'待结算',?)", (amount, amount, batch))
        con.execute("INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,gift_qty_entitled,gift_qty_actual,consistency,calc_batch_id) VALUES (2,0,0,98,98,'一致',2)")
        con.execute("INSERT INTO result_release_candidate(order_id,calc_date,is_candidate,reason,calc_batch_id) VALUES (2,'2026-10-02',1,'T-2',2)")
        con.execute("INSERT INTO result_fee(activity_id,actual_discount_total,gift_cost_total,settle_status,calc_batch_id) VALUES (2,0,NULL,'按赠品数量统计',2)")
        con.execute("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) VALUES ('O-money','差异','警告','金额差异','evidence',2)")
        con.execute("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) VALUES ('O-gift','未达释放节点','提示','待确认','evidence',2)")
        con.execute("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) VALUES ('UNKNOWN','批次问题','警告','无法归属','evidence',2)")
        con.commit(); con.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_activities_uses_requested_calculation_batch_and_keeps_gifts_as_quantities(self):
        payload = query_fee_tpm_activities(self.path, {'calc_batch_id': '2'})
        gift = next(row for row in payload['rows'] if row['activityId'] == 2)
        self.assertEqual(payload['calcBatchId'], 2)
        self.assertEqual(gift['benefitKind'], 'gift')
        self.assertIsNone(gift['tpm'])
        self.assertEqual(gift['giftQtyActual'], 98)

    def test_warning_blocks_settlement_and_tip_is_waiting_confirmation(self):
        rows = {row['activityId']: row for row in query_fee_tpm_activities(self.path, {'calc_batch_id': '2'})['rows']}
        self.assertEqual(rows[1]['status'], '待处理')
        self.assertEqual(rows[2]['status'], '待确认')
        self.assertEqual(query_fee_tpm_settlements(self.path, {'calc_batch_id': '2'})['rows'], [])

    def test_unattributable_issue_stays_in_response(self):
        issue = next(row for row in query_fee_tpm_issues(self.path, {'calc_batch_id': '2'})['rows'] if row['orderNo'] == 'UNKNOWN')
        self.assertIsNone(issue['activityId'])

    def test_missing_batch_is_not_found(self):
        with self.assertRaises(NotFoundError):
            query_fee_tpm_activities(self.path, {'calc_batch_id': '999'})


if __name__ == '__main__':
    unittest.main()


class FeeTpmRouteTests(FeeTpmQueryTests):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.path))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        super().tearDown()

    def test_fee_tpm_activity_detail_returns_404_for_an_unknown_activity(self):
        connection = HTTPConnection('127.0.0.1', self.server.server_address[1])
        connection.request('GET', '/api/fee-tpm/activities/999?calc_batch_id=2')
        response = connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 404)
        self.assertEqual(payload['error'], 'not_found')
