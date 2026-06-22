---
title: "koa-router 必知必会"
date: 2018-11-10T17:38:31+08:00
slug: "koa-router"
url: "/koa-router.html"
categories:
  - "归档"
  - "node"
tags:
  - "koa"
  - "router"
  - "node"
  - "npm"
hiddenFromHomePage: true
---

后台服务器都绕不开路由， 所以koa-router这个中间件是一定要了解的了。Github 地址: https://github.com/alexmingoia/koa-router 以下栗子都来自官网。最后附有一些tips。

##### 1.基本用法
![](koa-router/router1.png)

**技巧：const router = require('koa-router')()， 引入时在最后加一个括号，直接返回一个router实例，我们就不用去写  var router = new Router() 了，一个括号省了一行代码，赚了！**  

##### 2. router.verb

我们常用的 http 请求类型: get, post, put等，在router匹配这里直接可以写成 router.get(), router.post(), router.put() 来匹配。并且支持链式调用（这样分类去写review时候很方便）。
![](koa-router/router2.png)

 

##### 3.router 名字

每个路由都可以起一个名字，这样在使用起来直接"叫"它的名字，可以省去一大串的路径。

![](koa-router/router3.png)

 

##### 4.router 使用中间件

中间件诶，router可以用中间件，而且可以一口气用好几个中间件。不仅如此，还可以设置不同路由使用多个不同的中间件。下面第一个例子是单独对'/users/:id' 使用一个中间件。当然还可以接着使用多个中间件。

![](koa-router/router4.png)

下例是路由使用中间件的其它方法：

![](koa-router/router5.png)

 

##### 5.嵌套路由

Kou-router 的嵌套比起 vue-router 简单多了。其实就是两个路由的直接拼接。

![](koa-router/router6.png)
 

##### 6.路由前缀

Emmmmm 又是一个划算的代码片段，这样以后的路由就省了写'/users'

![](koa-router/router7.png)


##### 7.查找路由

router.route(): 根据路由的名字查找路由。如果存在，就反回一个layer类型的对象，结构如下。如果不存在返回false。

![](koa-router/router8.png)
 

##### 8.redirect 重定向

重定向方法需要区别 koa-router的 router.redirect 和 koa中原来的redirect。router.redirect(source, destination, [code]): source为源路由，destination是目的路由（可以是路由名字），code需要改变ctx的状态码，默认301。源代码如下：

![](koa-router/router9.png)


koa原来的redirect(url, alt): url是目标url（必须是具体的url），alt是对url为'back'的特殊次处理，默认状态码302。调用时直接用 cxt.redirect 即可，源代码如下：

![](koa-router/router10.png)

两个函数同一个目的，不同的参数。请选择使用。
 

##### 9.router.url 静态方法

返回一个具体的路径，可以配合redirect使用

![](koa-router/router11.png)

 