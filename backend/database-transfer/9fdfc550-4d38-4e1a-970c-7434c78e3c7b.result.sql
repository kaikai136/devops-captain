/* DevOps Captain Dump SQL
 Source Server Type: mysql
 Server Version: 8.0.30
 Date: 2026-10-20T05:00:54.659331+00:00
 File Encoding: UTF-8
*/

SET NAMES utf8mb4;
SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for t_company
-- ----------------------------
DROP TABLE IF EXISTS `t_company`;
CREATE TABLE `t_company` (
  `id` int NOT NULL AUTO_INCREMENT,
  `company_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '用户单位名称',
  `extra_info` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '其他扩展',
  `author` int DEFAULT NULL,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_company
-- ----------------------------
INSERT INTO `t_company` (`id`, `company_name`, `extra_info`, `author`, `create_time`, `update_time`) VALUES (-99, '南京讯思雅信息科技有限公司', NULL, -999, '2018-09-14 17:30:08', '2018-09-14 17:30:08');

-- ----------------------------
-- Table structure for t_sys_dict
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_dict`;
CREATE TABLE `t_sys_dict` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '编号',
  `value` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `label` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `description` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `sort` decimal(10,0) NOT NULL COMMENT '排序（升序）',
  `parent_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `create_by` int NOT NULL DEFAULT '1' COMMENT '更新者',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `update_by` int DEFAULT NULL COMMENT '备注信息',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '0' COMMENT '删除标记',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `sys_dict_value` (`value`) USING BTREE,
  KEY `sys_dict_label` (`label`) USING BTREE,
  KEY `sys_dict_del_flag` (`status`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='字典表';

-- ----------------------------
-- Records of t_sys_dict
-- ----------------------------
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (1, '1', '严重表述错误', 'error_word_type', '错别字类型', 1, NULL, '2024-07-15 17:51:11', 1, '2024-07-15 17:54:42', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (2, '2', '一般错误文字', 'error_word_type', '错别字类型', 2, NULL, '2024-07-15 17:55:39', 1, '2024-07-15 18:00:50', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (3, '11', '敏感词-非法网络广告类', 'sensitive_word_type', '敏感词类型', 1, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:19', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (4, '12', '敏感词-社会类', 'sensitive_word_type', '敏感词类型', 2, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:21', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (5, '13', '敏感词-违禁品信息类', 'sensitive_word_type', '敏感词类型', 3, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:25', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (6, '14', '敏感词-非法网址类', 'sensitive_word_type', '敏感词类型', 4, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:28', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (7, '15', '敏感词-邪教类', 'sensitive_word_type', '敏感词类型', 5, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:30', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (8, '16', '敏感词-色情类', 'sensitive_word_type', '敏感词类型', 6, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:34', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (9, '17', '敏感词-政治类', 'sensitive_word_type', '敏感词类型', 7, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:37', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (10, '18', '敏感词-暴恐类', 'sensitive_word_type', '敏感词类型', 8, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:39', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (11, '19', '敏感词-其它', 'sensitive_word_type', '敏感词类型', 9, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:43', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (12, '20', '敏感词-非法组织类', 'sensitive_word_type', '敏感词类型', 10, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:46', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (13, '21', '敏感词-赌博类', 'sensitive_word_type', '敏感词类型', 11, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:49', NULL, '0');
INSERT INTO `t_sys_dict` (`id`, `value`, `label`, `type`, `description`, `sort`, `parent_id`, `create_time`, `create_by`, `update_time`, `update_by`, `status`) VALUES (14, '32', '敏感词-隐私数据', 'sensitive_word_type', '敏感词类型', 12, NULL, '2024-07-15 17:55:39', 1, '2024-07-16 14:57:53', NULL, '0');

-- ----------------------------
-- Table structure for t_sys_group
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_group`;
CREATE TABLE `t_sys_group` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '唯一标识',
  `group_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `group_desc` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '分组描述',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_sys_group
-- ----------------------------
INSERT INTO `t_sys_group` (`id`, `group_name`, `group_desc`) VALUES (6, '管理员', '管理员');

-- ----------------------------
-- Table structure for t_sys_group_auth
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_group_auth`;
CREATE TABLE `t_sys_group_auth` (
  `id` int NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL COMMENT '分组ID',
  `menu_id` int NOT NULL COMMENT '菜单ID',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_sys_group_auth
-- ----------------------------

-- ----------------------------
-- Table structure for t_sys_menu
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_menu`;
CREATE TABLE `t_sys_menu` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '唯一标识',
  `menu_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '菜单名称',
  `url` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '菜单地址',
  `icon_class` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '样式类',
  `level` int DEFAULT NULL COMMENT '级别',
  `fid` int DEFAULT NULL COMMENT '父id',
  `order_code` int DEFAULT NULL COMMENT '排序值',
  `state` int DEFAULT NULL COMMENT '状态,1允许，0禁止',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_sys_menu
-- ----------------------------
INSERT INTO `t_sys_menu` (`id`, `menu_name`, `url`, `icon_class`, `level`, `fid`, `order_code`, `state`) VALUES (1, '系统管理', NULL, 'el-icon-setting', 0, NULL, 1, 1);
INSERT INTO `t_sys_menu` (`id`, `menu_name`, `url`, `icon_class`, `level`, `fid`, `order_code`, `state`) VALUES (2, '菜单管理', '/menu', 'fa fa-list', 1, 1, 1, 1);
INSERT INTO `t_sys_menu` (`id`, `menu_name`, `url`, `icon_class`, `level`, `fid`, `order_code`, `state`) VALUES (3, '用户管理', '/user', 'fa fa-user', 1, 1, 2, 1);
INSERT INTO `t_sys_menu` (`id`, `menu_name`, `url`, `icon_class`, `level`, `fid`, `order_code`, `state`) VALUES (4, '分组管理', '/group', 'fa fa-group', 1, 1, 3, 1);

-- ----------------------------
-- Table structure for t_sys_properties
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_properties`;
CREATE TABLE `t_sys_properties` (
  `id` int NOT NULL AUTO_INCREMENT,
  `key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `value` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `des` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `base` int DEFAULT '0' COMMENT '0.基础配置，不随环境变化 1.定制配置，不同环境配置不同',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `unique_key` (`key`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='配置表';

-- ----------------------------
-- Records of t_sys_properties
-- ----------------------------
INSERT INTO `t_sys_properties` (`id`, `key`, `value`, `des`, `base`, `update_time`) VALUES (1, 'identify.code-number', '4', '验证码位数', 0, '2021-03-26 09:38:41');
INSERT INTO `t_sys_properties` (`id`, `key`, `value`, `des`, `base`, `update_time`) VALUES (2, 'zimg.base-url', 'http://192.168.142.147:4869/', NULL, 0, '2021-03-16 16:58:14');

-- ----------------------------
-- Table structure for t_sys_user
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_user`;
CREATE TABLE `t_sys_user` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '唯一标识',
  `user_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户名',
  `password` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '密码',
  `email` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '邮箱',
  `company_id` int DEFAULT NULL COMMENT '公司编号',
  `real_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '注册人/企业联系人姓名',
  `mobilephone_number` char(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL COMMENT '手机号码',
  `group_id` int DEFAULT NULL COMMENT '分组id',
  `status` int unsigned DEFAULT NULL COMMENT '状态(0表示激活,1表示禁用,2表示锁定)',
  `role_id` tinyint(1) DEFAULT NULL COMMENT '角色(暂时没有用上)',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `expire_time` datetime DEFAULT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `user_name` (`user_name`) USING BTREE,
  UNIQUE KEY `email` (`email`) USING BTREE,
  UNIQUE KEY `mobilephone_number` (`mobilephone_number`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_sys_user
-- ----------------------------
INSERT INTO `t_sys_user` (`id`, `user_name`, `password`, `email`, `company_id`, `real_name`, `mobilephone_number`, `group_id`, `status`, `role_id`, `create_time`, `expire_time`) VALUES (-999, 'sysadmin', 'c12e01f2a13ff5587e1e9e4aedb8242d', NULL, -99, '超级管理员', NULL, 0, 0, NULL, NULL, NULL);

-- ----------------------------
-- Table structure for t_sys_user_auth
-- ----------------------------
DROP TABLE IF EXISTS `t_sys_user_auth`;
CREATE TABLE `t_sys_user_auth` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL COMMENT '用户id',
  `menu_id` int NOT NULL COMMENT '菜单id',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Records of t_sys_user_auth
-- ----------------------------

SET FOREIGN_KEY_CHECKS = 1;
