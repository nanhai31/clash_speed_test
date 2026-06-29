#!/usr/bin/env python3
import yaml
import requests
import time
import socket
import concurrent.futures
import sys
import os
import json
from typing import Dict, List, Tuple
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ClashSpeedTester:
    def __init__(self, config_url: str, max_latency: float = 500, 
                 top_n: int = None, max_workers: int = 20,
                 test_url: str = "http://www.google.com/generate_204"):
        self.config_url = config_url
        self.max_latency = max_latency
        self.top_n = top_n
        self.max_workers = max_workers
        self.test_url = test_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Clash-SpeedTest/1.0'
        })
        
    def download_config(self) -> Dict:
        """从URL下载配置文件"""
        logger.info(f"正在从 {self.config_url} 下载配置文件...")
        try:
            response = self.session.get(self.config_url, timeout=30)
            response.raise_for_status()
            
            # 尝试解析YAML
            config = yaml.safe_load(response.text)
            logger.info(f"成功下载配置文件，包含 {len(config.get('proxies', []))} 个节点")
            return config
        except requests.RequestException as e:
            logger.error(f"下载配置文件失败: {e}")
            sys.exit(1)
        except yaml.YAMLError as e:
            logger.error(f"解析YAML失败: {e}")
            sys.exit(1)
    
    def test_tcp_latency(self, node: Dict) -> Tuple[Dict, float]:
        """测试TCP连接延迟"""
        name = node.get('name', 'Unknown')
        server = node.get('server')
        port = node.get('port')
        
        if not server or not port:
            return node, float('inf')
        
        try:
            # DNS解析
            start_time = time.time()
            ip = socket.gethostbyname(server)
            dns_time = time.time() - start_time
            
            # TCP连接测试
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip, int(port)))
            conn_time = time.time() - start_time
            sock.close()
            
            if result == 0:
                total_time = (dns_time + conn_time) * 1000
                logger.debug(f"✓ {name}: {total_time:.2f}ms")
                return node, total_time
            else:
                logger.debug(f"✗ {name}: 连接失败")
                return node, float('inf')
                
        except socket.gaierror:
            logger.debug(f"✗ {name}: DNS解析失败")
            return node, float('inf')
        except socket.timeout:
            logger.debug(f"✗ {name}: 连接超时")
            return node, float('inf')
        except Exception as e:
            logger.debug(f"✗ {name}: 错误 - {str(e)}")
            return node, float('inf')
    
    def test_http_latency(self, node: Dict) -> Tuple[Dict, float]:
        """使用HTTP请求测试延迟（更准确）"""
        name = node.get('name', 'Unknown')
        
        # 构建代理URL（支持多种协议）
        proxy_url = self._build_proxy_url(node)
        if not proxy_url:
            return node, float('inf')
        
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        try:
            start_time = time.time()
            response = self.session.get(
                self.test_url,
                proxies=proxies,
                timeout=10,
                verify=False
            )
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code in [200, 204]:
                logger.debug(f"✓ {name}: {elapsed:.2f}ms")
                return node, elapsed
            else:
                logger.debug(f"✗ {name}: HTTP {response.status_code}")
                return node, float('inf')
                
        except requests.exceptions.Timeout:
            logger.debug(f"✗ {name}: HTTP请求超时")
            return node, float('inf')
        except requests.exceptions.ConnectionError:
            logger.debug(f"✗ {name}: HTTP连接失败")
            return node, float('inf')
        except Exception as e:
            logger.debug(f"✗ {name}: HTTP错误 - {str(e)}")
            return node, float('inf')
    
    def _build_proxy_url(self, node: Dict) -> str:
        """根据节点类型构建代理URL"""
        node_type = node.get('type', '').lower()
        server = node.get('server')
        port = node.get('port')
        
        if not server or not port:
            return None
        
        if node_type == 'ss':
            # Shadowsocks
            plugin = node.get('plugin')
            plugin_opts = node.get('plugin-opts', {})
            if plugin == 'obfs':
                return f"socks5://{server}:{port}"
            return f"ss://{node.get('cipher')}:{node.get('password')}@{server}:{port}"
        elif node_type == 'vmess':
            # VMess
            return f"socks5://{server}:{port}"
        elif node_type == 'trojan':
            # Trojan
            return f"socks5://{server}:{port}"
        elif node_type == 'socks5':
            # SOCKS5
            username = node.get('username')
            password = node.get('password')
            if username and password:
                return f"socks5://{username}:{password}@{server}:{port}"
            return f"socks5://{server}:{port}"
        else:
            # 默认使用SOCKS5
            return f"socks5://{server}:{port}"
    
    def test_nodes_parallel(self, nodes: List[Dict], use_http: bool = False) -> List[Tuple[Dict, float]]:
        """并行测试多个节点"""
        results = []
        test_func = self.test_http_latency if use_http else self.test_tcp_latency
        
        logger.info(f"开始测试 {len(nodes)} 个节点（{'HTTP' if use_http else 'TCP'}模式）...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_node = {
                executor.submit(test_func, node): node 
                for node in nodes
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_node):
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    
                    # 显示进度
                    if completed % 10 == 0 or completed == len(nodes):
                        logger.info(f"进度: {completed}/{len(nodes)} ({completed/len(nodes)*100:.1f}%)")
                        
                except Exception as e:
                    node = future_to_node[future]
                    logger.error(f"测试 {node.get('name', 'Unknown')} 时发生异常: {e}")
                    results.append((node, float('inf')))
        
        return results
    
    def filter_fast_nodes(self, results: List[Tuple[Dict, float]]) -> List[Dict]:
        """筛选延迟低的节点"""
        # 过滤掉无限延迟的节点
        valid_results = [(node, latency) for node, latency in results if latency < float('inf')]
        
        # 按延迟排序
        valid_results.sort(key=lambda x: x[1])
        
        # 筛选延迟小于阈值的节点
        fast_nodes = [(node, latency) for node, latency in valid_results if latency <= self.max_latency]
        
        if self.top_n:
            fast_nodes = fast_nodes[:self.top_n]
        
        logger.info("=" * 60)
        logger.info(f"找到 {len(fast_nodes)} 个可用节点 (延迟 ≤ {self.max_latency}ms):")
        logger.info("-" * 60)
        for i, (node, latency) in enumerate(fast_nodes, 1):
            logger.info(f"{i:3d}. {node['name'][:40]:<40} {latency:7.2f}ms")
        
        return [node for node, _ in fast_nodes]
    
    def create_new_config(self, original_config: Dict, fast_nodes: List[Dict]) -> Dict:
        """创建新的配置文件"""
        new_config = original_config.copy()
        
        # 更新节点列表
        new_config['proxies'] = fast_nodes
        
        # 更新 proxy-groups
        if 'proxy-groups' in new_config:
            for group in new_config['proxy-groups']:
                if 'proxies' in group:
                    original_proxies = group['proxies']
                    fast_node_names = {node['name'] for node in fast_nodes}
                    
                    # 保留特殊关键词
                    special_keywords = {'DIRECT', 'REJECT', 'GLOBAL', 'SELECT', 'PROXY'}
                    new_proxies = [
                        p for p in original_proxies 
                        if p in fast_node_names or p in special_keywords
                    ]
                    
                    # 确保至少有一个节点
                    if not new_proxies and fast_nodes:
                        new_proxies = [fast_nodes[0]['name']]
                    
                    group['proxies'] = new_proxies
        
        # 添加元数据
        if 'mixed-port' not in new_config:
            new_config['mixed-port'] = 7890
        if 'allow-lan' not in new_config:
            new_config['allow-lan'] = False
        if 'mode' not in new_config:
            new_config['mode'] = 'rule'
        if 'log-level' not in new_config:
            new_config['log-level'] = 'info'
        
        return new_config
    
    def save_config(self, config: Dict, output_path: str):
        """保存配置文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False, 
                         default_flow_style=False, width=1000)
            
            logger.info(f"✓ 配置文件已保存: {output_path}")
            
            # 保存统计信息
            stats = {
                'timestamp': datetime.now().isoformat(),
                'total_nodes': len(config.get('proxies', [])),
                'config_url': self.config_url,
                'max_latency': self.max_latency
            }
            
            stats_path = output_path.replace('.yaml', '_stats.json')
            with open(stats_path, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ 统计信息已保存: {stats_path}")
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise
    
    def run(self, output_path: str = "config/fast_config.yaml", use_http: bool = True):
        """运行完整的测试流程"""
        start_time = time.time()
        
        # 1. 下载配置
        config = self.download_config()
        
        if 'proxies' not in config or not config['proxies']:
            logger.error("配置文件中没有找到节点(proxies)")
            sys.exit(1)
        
        nodes = config['proxies']
        logger.info(f"加载了 {len(nodes)} 个节点")
        
        # 2. 测试节点延迟
        results = self.test_nodes_parallel(nodes, use_http)
        
        # 3. 筛选快速节点
        fast_nodes = self.filter_fast_nodes(results)
        
        if not fast_nodes:
            logger.warning("⚠ 没有找到可用的快速节点!")
            # 如果没有可用节点，保留延迟最低的10个
            sorted_results = sorted([r for r in results if r[1] < float('inf')], key=lambda x: x[1])
            if sorted_results:
                fast_nodes = [node for node, _ in sorted_results[:10]]
                logger.info(f"已选择延迟最低的 {len(fast_nodes)} 个节点")
            else:
                logger.error("❌ 所有节点均不可用，退出")
                sys.exit(1)
        
        # 4. 创建新配置
        new_config = self.create_new_config(config, fast_nodes)
        
        # 5. 保存新配置
        self.save_config(new_config, output_path)
        
        # 输出总结
        elapsed_time = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"完成! 耗时: {elapsed_time:.2f}秒")
        logger.info(f"原始节点数: {len(nodes)}")
        logger.info(f"快速节点数: {len(fast_nodes)}")
        logger.info(f"输出文件: {output_path}")
        
        return output_path

def main():
    # 从环境变量获取配置
    CONFIG_URL = os.environ.get('CONFIG_URL', 'https://127.0.0.1/github/config.yaml')
    MAX_LATENCY = float(os.environ.get('MAX_LATENCY', '500'))
    TOP_N = os.environ.get('TOP_N')
    TOP_N = int(TOP_N) if TOP_N and TOP_N.isdigit() else None
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '20'))
    OUTPUT_PATH = os.environ.get('OUTPUT_PATH', 'config/fast_config.yaml')
    USE_HTTP = os.environ.get('USE_HTTP', 'true').lower() == 'true'
    TEST_URL = os.environ.get('TEST_URL', 'http://www.google.com/generate_204')
    
    # 验证URL
    if not CONFIG_URL.startswith(('http://', 'https://')):
        logger.error(f"无效的URL: {CONFIG_URL}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Clash 节点自动测速工具 (GitHub Actions版)")
    logger.info("=" * 60)
    logger.info(f"配置文件URL: {CONFIG_URL}")
    logger.info(f"最大延迟阈值: {MAX_LATENCY}ms")
    logger.info(f"保留节点数: {TOP_N if TOP_N else '全部合格'}")
    logger.info(f"并发线程数: {MAX_WORKERS}")
    logger.info(f"测试模式: {'HTTP' if USE_HTTP else 'TCP'}")
    logger.info(f"测试URL: {TEST_URL}")
    logger.info("=" * 60)
    
    # 创建测试器并运行
    tester = ClashSpeedTester(
        config_url=CONFIG_URL,
        max_latency=MAX_LATENCY,
        top_n=TOP_N,
        max_workers=MAX_WORKERS,
        test_url=TEST_URL
    )
    
    try:
        output_file = tester.run(OUTPUT_PATH, USE_HTTP)
        
        # 设置GitHub Actions输出变量
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"config_file={output_file}\n")
                f.write(f"timestamp={datetime.now().isoformat()}\n")
        
    except Exception as e:
        logger.error(f"运行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
