"""
随堂测试解析器
支持口语化、JSON、CSV等多种格式的解析
"""

import re
from datetime import datetime, date
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

from .database import get_trade_record_by_id, update_trade_record


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    confidence: float  # 0-1 置信度
    data: Optional[Dict[str, Any]]
    missing_fields: list  # 缺失的字段
    error_message: str = ""


# 股票名称到代码的映射（常见股票）
STOCK_NAME_MAP = {
    "茅台": "600519.SH",
    "贵州茅台": "600519.SH",
    "平安": "601318.SH",
    "万科": "000002.SZ",
    "宁德": "300750.SZ",
    "宁德时代": "300750.SZ",
    "隆基": "601012.SH",
    "隆基绿能": "601012.SH",
    "比亚迪": "002594.SZ",
    "招行": "600036.SH",
    "招商银行": "600036.SH",
    "五粮液": "000858.SZ",
    "海康": "002415.SZ",
    "海康威视": "002415.SZ",
}


class TradeParser:
    """随堂测试解析器"""

    def __init__(self):
        self.name_to_code = STOCK_NAME_MAP

    def parse(self, text: str) -> ParseResult:
        """
        解析用户输入的交易记录

        Args:
            text: 用户输入的文字

        Returns:
            ParseResult: 解析结果
        """
        # 优先级1: JSON格式
        if self._is_json(text):
            return self._parse_json(text)

        # 优先级2: CSV/表格格式
        if self._is_csv(text):
            return self._parse_csv(text)

        # 优先级3: 口语化描述（最高优先级）
        return self._parse_natural(text)

    def _is_json(self, text: str) -> bool:
        """判断是否为JSON格式"""
        text = text.strip()
        return (text.startswith('{') and text.endswith('}')) or \
               (text.startswith('[') and text.endswith(']'))

    def _is_csv(self, text: str) -> bool:
        """判断是否为CSV/表格格式"""
        lines = text.strip().split('\n')
        if len(lines) < 2:
            return False

        # 检查是否有明显的分隔符
        for sep in ['|', '\t', ',']:
            if sep in lines[0] and sep in lines[1]:
                return True
        return False

    def _parse_json(self, text: str) -> ParseResult:
        """解析JSON格式"""
        import json
        try:
            data = json.loads(text)
            if isinstance(data, list):
                data = data[0]  # 取第一个元素

            # 映射字段
            mapped = self._map_fields(data)

            # 检查必填字段
            missing = self._check_required_fields(mapped)
            confidence = 1.0 if not missing else 0.7

            return ParseResult(
                success=True,
                confidence=confidence,
                data=mapped,
                missing_fields=missing
            )
        except json.JSONDecodeError as e:
            return ParseResult(
                success=False,
                confidence=0,
                data=None,
                missing_fields=[],
                error_message=f"JSON解析失败: {str(e)}"
            )

    def _parse_csv(self, text: str) -> ParseResult:
        """解析CSV/表格格式"""
        try:
            lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

            # 确定分隔符
            sep = '|'
            if '\t' in lines[0]:
                sep = '\t'
            elif ',' in lines[0]:
                sep = ','

            # 解析标题行
            headers = [h.strip() for h in lines[0].split(sep)]

            # 解析数据行（取第一行）
            values = [v.strip() for v in lines[1].split(sep)]

            data = dict(zip(headers, values))
            mapped = self._map_fields(data)

            missing = self._check_required_fields(mapped)
            confidence = 0.9 if not missing else 0.6

            return ParseResult(
                success=True,
                confidence=confidence,
                data=mapped,
                missing_fields=missing
            )
        except Exception as e:
            return ParseResult(
                success=False,
                confidence=0,
                data=None,
                missing_fields=[],
                error_message=f"CSV解析失败: {str(e)}"
            )

    def _parse_natural(self, text: str) -> ParseResult:
        """解析口语化描述（最高优先级）"""
        data = {}
        missing = []
        errors = []

        # 日期提取
        date_patterns = [
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{1,2}[月/-]\d{1,2}[日/-]?)',
            r'今天|昨天|前天|前日',
            r'今儿|昨儿'
        ]

        today = datetime.now()
        date_str = None

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                if match.groups():
                    date_text = match.group(1)
                else:
                    date_text = match.group(0)
                if '今天' in date_text or '今儿' in text:
                    date_str = today.strftime('%Y-%m-%d')
                elif '昨天' in date_text or '昨儿' in text:
                    date_str = (today.replace(day=today.day - 1)).strftime('%Y-%m-%d')
                elif '前天' in date_text or '前日' in text:
                    date_str = (today.replace(day=today.day - 2)).strftime('%Y-%m-%d')
                elif '-' in date_text or '/' in date_text:
                    if len(date_text) == 10:  # yyyy-mm-dd
                        date_str = date_text.replace('/', '-')
                    else:  # mm-dd 或 m-d
                        parts = re.split(r'[-/]', date_text)
                        if len(parts) == 2:
                            date_str = f"{today.year}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                break

        if date_str:
            data['trade_date'] = date_str
        else:
            missing.append('trade_date')
            data['trade_date'] = today.strftime('%Y-%m-%d')  # 默认今天

        # 股票代码提取
        code_patterns = [
            r'([012]\d{5})',  # 6位数字代码
            r'（(\d{6})）',  # 中文括号
            r'\((\d{6})\)'  # 英文括号
        ]

        ts_code = None
        for pattern in code_patterns:
            match = re.search(pattern, text)
            if match:
                ts_code = match.group(1)
                break

        # 尝试从股票名称匹配
        for name, code in self.name_to_code.items():
            if name in text:
                ts_code = code
                if 'name' not in data:
                    data['name'] = name
                break

        if ts_code:
            # 标准化代码格式
            if len(ts_code) == 6:
                if ts_code.startswith('0') or ts_code.startswith('3'):
                    ts_code = f"{ts_code}.SZ"
                elif ts_code.startswith('6'):
                    ts_code = f"{ts_code}.SH"
                elif ts_code.startswith('4') or ts_code.startswith('8'):
                    ts_code = f"{ts_code}.BJ"
            data['ts_code'] = ts_code
        else:
            missing.append('ts_code')

        # 交易方向
        action = None
        if '买' in text:
            action = 'BUY'
            data['action'] = 'BUY'
        elif '卖' in text:
            action = 'SELL'
            data['action'] = 'SELL'

        if not action:
            missing.append('action')

        # 价格提取
        price_patterns = [
            r'(\d+(?:\.\d{1,2})?)\s*(?:元|块|块)',
            r'价格[是为]*\s*(\d+(?:\.\d{1,2})?)',
            r'@\s*(\d+(?:\.\d{1,2})?)',
        ]

        price = None
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                price = float(match.group(1))
                break

        if price:
            data['price'] = price
        else:
            missing.append('price')

        # 数量提取
        qty_patterns = [
            r'(\d+)\s*(?:股|手)',
            r'数量\s*(\d+)',
            r'买了?\s*(\d+)',
            r'卖[出]?\s*(\d+)',
        ]

        quantity = None
        for pattern in qty_patterns:
            match = re.search(pattern, text)
            if match:
                quantity = int(match.group(1))
                break

        if quantity:
            data['quantity'] = quantity
        else:
            missing.append('quantity')

        # 计算金额
        if price and quantity:
            data['amount'] = round(price * quantity, 2)

        # 置信度计算
        if not data.get('ts_code') or not data.get('action'):
            confidence = 0.4
        elif missing:
            confidence = 0.6
        else:
            confidence = 0.85  # 口语化总有不确定性

        return ParseResult(
            success=True,
            confidence=confidence,
            data=data if data else None,
            missing_fields=missing,
            error_message=",".join(errors) if errors else ""
        )

    def _map_fields(self, data: Dict) -> Dict:
        """映射字段名到标准格式"""
        field_mapping = {
            'code': 'ts_code',
            '股票代码': 'ts_code',
            'date': 'trade_date',
            '日期': 'trade_date',
            'time': 'trade_date',
            'action': 'action',
            'type': 'action',
            '买卖': 'action',
            '买入': 'action',
            '卖出': 'action',
            'price': 'price',
            '单价': 'price',
            '成交价': 'price',
            'quantity': 'quantity',
            'num': 'quantity',
            '数量': 'quantity',
            '股数': 'quantity',
            '股': 'quantity',
            'amount': 'amount',
            '金额': 'amount',
            'total': 'amount',
            'name': 'name',
            '股票名称': 'name',
            '证券名称': 'name',
        }

        mapped = {}
        for key, value in data.items():
            mapped_key = field_mapping.get(key, key)
            mapped[mapped_key] = value

        # 标准化 action
        if 'action' in mapped:
            action = str(mapped['action']).upper()
            if '买' in action:
                mapped['action'] = 'BUY'
            elif '卖' in action:
                mapped['action'] = 'SELL'

        # 标准化 ts_code 格式
        if 'ts_code' in mapped:
            code = str(mapped['ts_code'])
            if len(code) == 6 and '.' not in code:
                if code.startswith('0') or code.startswith('3'):
                    mapped['ts_code'] = f"{code}.SZ"
                elif code.startswith('6'):
                    mapped['ts_code'] = f"{code}.SH"
                elif code.startswith('4') or code.startswith('8'):
                    mapped['ts_code'] = f"{code}.BJ"

        return mapped

    def _check_required_fields(self, data: Dict) -> list:
        """检查必填字段"""
        required = ['trade_date', 'ts_code', 'action', 'price', 'quantity']
        missing = []

        for field in required:
            if field not in data or not data[field]:
                missing.append(field)

        return missing

    def confirm_and_fill(self, data: Dict, user_response: str) -> Dict:
        """
        根据用户的确认/修正信息更新数据

        Args:
            data: 当前数据
            user_response: 用户回复

        Returns:
            更新后的数据
        """
        # 确认词
        confirm_words = ['对', '是的', '正确', '嗯', '好', 'ok', 'confirm']
        # 否定词
        deny_words = ['不', '不是', '错', 'no', '不对']

        response = user_response.strip().lower()

        # 如果用户确认
        if any(w in response for w in confirm_words):
            return data

        # 如果用户否定，尝试从回复中提取修正值
        for key in data.keys():
            if key in user_response:
                # 简单处理：假设用户输入了修正值
                pass

        return data

    def generate_confirm_message(self, data: Dict) -> str:
        """生成确认消息"""
        lines = []

        if 'trade_date' in data:
            lines.append(f"日期: {data['trade_date']}")
        if 'ts_code' in data:
            name = data.get('name', data['ts_code'])
            lines.append(f"股票: {name} ({data['ts_code']})")
        if 'action' in data:
            action_text = "买入" if data['action'] == 'BUY' else "卖出"
            lines.append(f"方向: {action_text}")
        if 'price' in data:
            lines.append(f"价格: {data['price']}元")
        if 'quantity' in data:
            lines.append(f"数量: {data['quantity']}股")
        if 'amount' in data:
            lines.append(f"金额: {data['amount']}元")

        return "确认一下：" + "，".join(lines)


def format_trade_for_review(data: Dict) -> str:
    """格式化交易数据用于Z哥点评"""
    action_text = "买入" if data.get('action') == 'BUY' else "卖出"
    name = data.get('name', data.get('ts_code', ''))
    ts_code = data.get('ts_code', '')

    lines = [
        f"📋 交易记录确认",
        f"",
        f"📅 日期: {data.get('trade_date', '未设置')}",
        f"📈 股票: {name} ({ts_code})",
        f"📊 方向: {action_text}",
        f"💰 价格: {data.get('price', '?')}元",
        f"🔢 数量: {data.get('quantity', '?')}股",
    ]

    if 'amount' in data:
        lines.append(f"💵 金额: {data['amount']}元")

    if 'reason' in data and data['reason']:
        lines.append(f"📝 原因: {data['reason']}")

    return "\n".join(lines)