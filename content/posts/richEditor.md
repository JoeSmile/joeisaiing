---
title: "rich editor(富文本编辑器)"
date: 2019-08-21T12:27:10+08:00
slug: "richEditor"
url: "/richEditor.html"
categories:
  - "javascript"
tags:
  - "编辑器"
  - "solutions"
  - "富文本编辑器"
  - "npm"
featuredImage: "/images/covers/xiaoxin.jpg"
---

今天我们来介绍5个前端富文本编辑器

#### 1.vue-quill-editor   
*地址：https://github.com/surmon-china/vue-quill-editor*

这款富文本编辑器，能搞定 vue 的 SPA 和 SSR 富文本编辑问题。使用起来很方便。文档易懂，要深入了解就要详细的看看quill的文档了，和quill一样可以通过注册组件来扩展功能。不过quill目前的release版本是1.3.6，vue-quill-editor依赖的是1.3.4 部分扩展组建用起来可能会有隐藏的bug。如果想深入了解推荐看1.3.4版本的quill。目前的版本改动较大。不过，这款编辑器和quill一样，对table的支持不太友好。扩展quilljs-table有蛮多bug，全选删除会留下一行表格，怎么都删不掉，该起来源代码也不那么容易。如果需要用到table功能，不建议使用quill系列的编辑器。
![](richEditor/quill1.png)

---
#### 2.Quill 近2万颗星星的 富文本编辑器 
*地址：https://quilljs.com/*

quill是vue-quill-editor的核心，功能强大，如果想自己更灵活的使用编辑器可以直接使用quill，封装成自己的组件。没的说，除了table其它都很棒。目前quill正在集成table的相关功能，预计很快就可以添上这个坑了。
![](richEditor/quill2.png)

---
#### 3.TinyMCE https://www.tiny.cloud/

这款编辑器个人感觉比以上两款都要强大，很贴心的有两种模式。一个是普通模式，一个是inline模式。在inline模式中，在需要编辑时功能菜单可以浮动起来，在readonly时功能菜单隐藏。此编辑器对table友好（有没有很感动）。有些高级功能是需要付费的，详见官网。这个组件也有个小问题。场景：当插入图片后，把编辑的content保存起来，在其它<div>标签或者<per>标签内显示（非TinyMCE内）图片环绕着的文子会错位。这个很影响美观。不过从word 和 excel 复制粘贴过来的内容完全匹配。
 
line模式
![](richEditor/quill3.png)

---
#### 4.wangEditor 国产轻量级编辑器

使用起来很走心，很简单，中文文档详细 https://www.kancloud.cn/wangfupeng/wangeditor3/332599  学习成本较以上3个小了很多。table和图片处理都OK。近6000个star可以证明这款编辑器经过考验了。
![](richEditor/quill4.png)

---
#### 5.UEditor 百度编辑器，符合国人习惯，强大的无可挑剔 
*地址：http://fex.baidu.com/ueditor/#start-start*

![](richEditor/quill5.png)
看图！ 有木有和word一摸一样。能想到的功能基本都有了。本人在wordpress 用的就是这个款编辑器。UEditor可以支持前后端集成，支持php，jsp等。如果项目中需要非常专业的编辑功能，这个编辑器肯定是首选了！
