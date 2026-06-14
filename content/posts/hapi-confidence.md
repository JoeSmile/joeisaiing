---
title: "hapi-confidence"
date: 2019-09-16T10:46:51+08:00
slug: "hapi-confidence"
url: "/hapi-confidence.html"
featuredImage: "/images/covers/confidence_logo.png"
---

> 记录一个confidence插件，简单明了地根据不同环境变量更换配置。平时我们写 config 或者 settings 文件要仔细区分环境，参数值比较混乱，难管理。有了 confidence 插件之后，再也不用担心环境参数混乱的问题了。

**confidence 地址**   
https://github.com/hapipal/confidence


## 基本结构
结构很清晰，根据不同的环境变量获取不同的值。还能做一些范围控制。使用起来很简单，只要配置**标准参数**(如:$filter)即可。
``` js
{
    "key1": "abc",
    "key2": {
        "$filter": "env",
        "production": {
            "deeper": {
                "$value": "value"
            }
        },
        "$default": {
            "$filter": "platform",
            "android": 0,
            "ios": 1,
            "$default": 2
        }
    },
    "ab": {
        "$filter": "random.a",
        "$range": [
            { "limit": 10, "value": 4 },
            { "limit": 20, "value": 5 }
        ],
        "$default": 6
    },
    "$meta": {
        "description": "example file"
    }
}
```

## API
我们在使用confidence之前，先介绍下它的API
> new Store(document) 创建一个配置容器   
> store.load(document) 载入一份配置文件  
> store.get() 根据参数生成配置   

```js
// 一个简单的demo
const { Store } = require('confidence')
const { env } = process
// 从环境变量取值
const criteria = {
  env: env.NODE_ENV
}
const settings = {
  platform: {
    $filter: 'env',
    development: 'this is DEV environment',
    qa: 'this is in QA environment',
    production: 'this is in PRO environment',
    $default: 'this is in LOCAL environment'
  }
}
// 创建配置容器
const store = new Store(settings)

module.exports = {
  settings: store.get('/', criteria) //根据环境变量生成对应的配置
}
// settings 结构为 { platform: 'this is in DEV environment' }
```


## 标准参数
### filter
> 规则：变量名只能用 字母 和 '_'。根据匹配环境变量的值，来选择用什么变量。（看个栗子瞬间就懂）


``` js
platform: {
  $filter: 'NODE_ENV',
  development: 'this is DEV environment',
  qa: 'this is in QA environment',
  production: 'this is in PRO environment',
  $default: 'this is in LOCAL environment'
}
```
> 在终端执行export，会把所有的环境变量打印出来，观察下 NODE_ENV 的值，本人本地的 NODE_ENV 值是 dev， 故直接用default值。   
> 最终结果： { platform: 'this is in LOCAL environment' }

PS: 把$filter 当作 switch-case 语句就好理解了。


### range
先上个栗子
```js
key: {
    "$filter": "random",
    "$range": [
        { "limit": 10, "value": 4 },
        { "limit": 20, "value": 5 }
    ],
    "$default": 6
}
```
> 当 random 小于等于10，key的值为4；   
> 当 random 大于10并且小于等于20， key的值为5；   
> 当 random 大于20，key的值为6

### Shared values（$base）
用栗子说明问题
``` js
{
  "$filter": "env",
  "$base": {
      "logLocation": "/logs"
  },
  "production":  {
      "logLevel": "error"
  },
  "qa":  {
      "logLevel": "info",
      "logLocation": "/qa/logs"
  },
  "staging":  {
      "logLevel": "debug"
  }
}
```
当写了$base，以下的条件中如果不覆写 logLocation, 就默认有一个"logLocation": "/logs" 属性。    
所以当 env 是 production 时，结果为   
```js 
{ 
  "logLevel": "error",
  "logLocation": "/logs"
}
```
当 env 是 qa 时，结果为
``` js
{
  "logLevel": "info",
  "logLocation": "/qa/logs"
}
```

## 总结
使用confidence设置配置文件快捷方便，清晰明了，node型框架(hapi or koa)统统适用。

### 最后
这里有一个 hapi 小型脚手架，包含confidence插件， Glue插件等，练手好demo！   
demo传送门 https://github.com/JoeSmile/hapi-confidence
