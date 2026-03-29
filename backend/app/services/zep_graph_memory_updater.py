"""
Zep graph memory update service
Dynamically update Agent activities from simulation to Zep graph
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.zep_graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent activity record"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Convert activity to text description for Zep
        
        Use natural language description format so Zep can extract entities and relationships
        Do not add simulation-related prefixes to avoid misleading graph updates
        """
        # Generate different descriptions based on action type
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # Directly return "agent name: activity description" format without simulation prefix
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"Published a post: "{content}""
        return "Published a post"
    
    def _describe_like_post(self) -> str:
        """Like post - includes post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"Liked {post_author}'s post: "{post_content}""
        elif post_content:
            return f"Liked a post: "{post_content}""
        elif post_author:
            return f"Liked {post_author}'s post"
        return "Liked a post"
    
    def _describe_dislike_post(self) -> str:
        """Dislike post - includes post content and author info"""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"Disliked {post_author}'s post: "{post_content}""
        elif post_content:
            return f"Disliked a post: "{post_content}""
        elif post_author:
            return f"Disliked {post_author}'s post"
        return "Disliked a post"
    
    def _describe_repost(self) -> str:
        """Repost - includes original content and author info"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"Reposted {original_author}'s post: "{original_content}""
        elif original_content:
            return f"Reposted a post: "{original_content}""
        elif original_author:
            return f"Reposted {original_author}'s post"
        return "Reposted a post"
    
    def _describe_quote_post(self) -> str:
        """Quote post - includes original content, author info, and quote comment"""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"Quoted {original_author}'s post"{original_content}""
        elif original_content:
            base = f"Quoted a post"{original_content}""
        elif original_author:
            base = f"Quoted {original_author}'s post"
        else:
            base = "Quoted a post"
        
        if quote_content:
            base += f", and commented:"{quote_content}""
        return base
    
    def _describe_follow(self) -> str:
        """Follow user - includes followed user name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"Followed user "{target_user_name}""
        return "Followed a user"
    
    def _describe_create_comment(self) -> str:
        """Post comment - includes comment content and commented post info"""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"On {post_author}'s post"{post_content}" commented:"{content}""
            elif post_content:
                return f"On post "{post_content}" commented:"{content}""
            elif post_author:
                return f"On {post_author}'s post commented:"{content}""
            return f"Commented:"{content}""
        return "Posted a comment"
    
    def _describe_like_comment(self) -> str:
        """Like comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"Liked {comment_author}'s comment:"{comment_content}""
        elif comment_content:
            return f"Liked a comment:"{comment_content}""
        elif comment_author:
            return f"Liked {comment_author}'s comment"
        return "Liked a comment"
    
    def _describe_dislike_comment(self) -> str:
        """Dislike comment - includes comment content and author info"""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"Disliked {comment_author}'s comment:"{comment_content}""
        elif comment_content:
            return f"Disliked a comment:"{comment_content}""
        elif comment_author:
            return f"Disliked {comment_author}'s comment"
        return "Disliked a comment"
    
    def _describe_search(self) -> str:
        """Search posts - 包含Search keyword"""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"search了"{query}"" if query else "Performed a search"
    
    def _describe_search_user(self) -> str:
        """Search user - 包含Search keyword"""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"Searched for user"{query}"" if query else "Searched for user"
    
    def _describe_mute(self) -> str:
        """Mute user - 包含被Mute user的name"""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"Muted user "{target_user_name}""
        return "Muted 一user "
    
    def _describe_generic(self) -> str:
        # 对于Unknown的动作type，生成通用description
        return f"执行了{self.action_type}operation"


class ZepGraphMemoryUpdater:
    """
    ZepGraph memory updater
    
    监控模拟的actions日志file，将新的agentactivity实时update到Zep图谱中。
    按平台分组，每累积BATCH_SIZE activities后批量Send to Zep。
    
    所有有意义的行为都会被update到Zep，action_args中会包含完整的上下文info:
    - Liked/Disliked's post原文
    - Reposted/Quoted's post原文
    - 关注/屏蔽的user名
    - Liked/Disliked's comment原文
    """
    
    # 批量发送大小(每平台累积多少条后发送)
    BATCH_SIZE = 5
    
    # 平台name映射(用于控制台显示)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': '世界1',
        'reddit': '世界2',
    }
    
    # 发送间隔(秒)，避免request过快
    SEND_INTERVAL = 0.5
    
    # Retry config
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        初始化update器
        
        Args:
            graph_id: Zep graph ID
            api_key: Zep API Key(Options，Default从config读取)
        """
        self.graph_id = graph_id
        self.api_key = api_key or Config.ZEP_API_KEY
        
        if not self.api_key:
            raise ValueError("ZEP_API_KEY is not configured")
        
        self.client = Zep(api_key=self.api_key)
        
        # Activity queue
        self._activity_queue: Queue = Queue()
        
        # 按平台分组的activity缓冲区(每平台各自累积到BATCH_SIZE后批量发送)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # 控制标志
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._total_activities = 0  # 实际添加到队列的activity数
        self._total_sent = 0        # SuccessSend to Zep的批次数
        self._total_items_sent = 0  # SuccessSend to Zep的activity条数
        self._failed_count = 0      # 发送failed的批次数
        self._skipped_count = 0     # 被过滤跳过的activity数(DO_NOTHING)
        
        logger.info(f"ZepGraphMemoryUpdater 初始化完成: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """Retrieved平台的显示name"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """启动后台工作线程"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"ZepMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"ZepGraphMemoryUpdater started: graph_id={self.graph_id}")
    
    def stop(self):
        """停止后台工作线程"""
        self._running = False
        
        # 发送剩余的activity
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"ZepGraphMemoryUpdater stopped: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        添加一agentactivity到队列
        
        所有有意义的行为都会被添加到队列，Including:
        - CREATE_POST(发帖)
        - CREATE_COMMENT(comment)
        - QUOTE_POST(Quotedpost)
        - SEARCH_POSTS(Search posts)
        - SEARCH_USER(Search user)
        - LIKE_POST/DISLIKE_POST(Liked/Dislikedpost)
        - REPOST(Reposted)
        - FOLLOW(关注)
        - MUTE(屏蔽)
        - LIKE_COMMENT/DISLIKE_COMMENT(Liked/Disliked评论)
        
        action_args中会包含完整的上下文info(如post原文, user名等)。
        
        Args:
            activity: Agent activity record
        """
        # 跳过DO_NOTHINGtype的activity
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"添加activity到Zep队列: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        从dictdata添加activity
        
        Args:
            data: 从actions.jsonl解析的dictdata
            platform: 平台name (twitter/reddit)
        """
        # 跳过事件type的条目
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """后台工作循环 - 按平台批量发送activity到Zep"""
        while self._running or not self._activity_queue.empty():
            try:
                # 尝试从队列Retrievedactivity(超时1秒)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # 将activity添加到对应平台的缓冲区
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # check该平台是否达到Batch size
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # 释放锁后再发送
                            self._send_batch_activities(batch, platform)
                            # 发送间隔，避免request过快
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f"工作循环异常: {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Batch send activities to Zep graph(合并为a 条文本)
        
        Args:
            activities: Agentactivitylist
            platform: 平台name
        """
        if not activities:
            return
        
        # 将多 activities合并为a 条文本，用换行分隔
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)
        
        # 带重试的发送
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f"Success批量发送 {len(activities)} 条{display_name}activity到图谱 {self.graph_id}")
                logger.debug(f"批量content预览: {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"批量Send to Zepfailed (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"批量Send to Zepfailed，已重试{self.MAX_RETRIES}次: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """发送队列和缓冲区中剩余的activity"""
        # 首先处理队列中剩余的activity，添加到缓冲区
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # 然后发送各平台缓冲区中剩余的activity(即使不足BATCH_SIZE条)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"发送{display_name}平台剩余的 {len(buffer)}  activities")
                    self._send_batch_activities(buffer, platform)
            # 清空所有缓冲区
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Retrieved统计info"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # 添加到队列的activity总数
            "batches_sent": self._total_sent,            # Success发送的批次数
            "items_sent": self._total_items_sent,        # Success发送的activity条数
            "failed_count": self._failed_count,          # 发送failed的批次数
            "skipped_count": self._skipped_count,        # 被过滤跳过的activity数(DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # 各平台缓冲区大小
            "running": self._running,
        }


class ZepGraphMemoryManager:
    """
    管理多模拟的ZepGraph memory updater
    
    每模拟可以有自己的update器instance
    """
    
    _updaters: Dict[str, ZepGraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> ZepGraphMemoryUpdater:
        """
        为模拟createGraph memory updater
        
        Args:
            simulation_id: Simulation ID
            graph_id: Zep graph ID
            
        Returns:
            ZepGraphMemoryUpdaterinstance
        """
        with cls._lock:
            # ifalready exists，先停止旧的
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = ZepGraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"createGraph memory updater: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[ZepGraphMemoryUpdater]:
        """Retrieved模拟的update器"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """停止并移除模拟的update器"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"stoppedGraph memory updater: simulation_id={simulation_id}")
    
    # 防止 stop_all 重复调用的标志
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """停止所有update器"""
        # 防止重复调用
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"停止update器failed: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("stopped所有Graph memory updater")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Retrieved所有update器的统计info"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }
